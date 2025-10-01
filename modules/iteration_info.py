import os
import requests
from pymongo import MongoClient
import streamlit as st
from datetime import datetime
import logging
import base64

# --------------------------------------------------------
# Setup logging (this will log to Streamlit console or server logs)
# --------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load secrets from Streamlit
org_url = st.secrets["ado"]["organization_url"]
project = st.secrets["ado"]["project_name"]
personal_access_token = st.secrets["ado"]["ado_pat"]

mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]
collection_name = "iteration-data"

# --------------------------------------------------------
# Mongo connection
# --------------------------------------------------------
client = MongoClient(mongo_uri)
db = client[db_name]

if collection_name not in db.list_collection_names():
    db.create_collection(collection_name)

collection = db[collection_name]

# --------------------------------------------------------
# Auth header for ADO
# --------------------------------------------------------
pat_bytes = f":{personal_access_token}".encode("utf-8")
headers = {
    "Content-Type": "application/json",
    "Authorization": "Basic " + base64.b64encode(pat_bytes).decode("utf-8")
}


def get_iterations():
    """Get all iterations for the project."""
    url = f"{org_url}/{project}/_apis/work/teamsettings/iterations?api-version=7.0"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])


def get_work_items_for_iteration(iteration_path):
    """Get all work items for a given iteration path using WIQL + batch API."""
    wiql = {
        "query": f"""
        SELECT [System.Id], [System.WorkItemType], [System.State], 
               [Microsoft.VSTS.Scheduling.Effort], [Microsoft.VSTS.Common.ClosedDate]
        FROM WorkItems
        WHERE [System.TeamProject] = '{project}'
        AND [System.IterationPath] = '{iteration_path}'
        """
    }

    url = f"{org_url}/{project}/_apis/wit/wiql?api-version=7.0"
    response = requests.post(url, headers=headers, json=wiql)
    response.raise_for_status()
    work_items = response.json().get("workItems", [])

    if not work_items:
        return []

    # Batch get work item details
    ids = ",".join(str(wi["id"]) for wi in work_items)
    url = f"{org_url}/_apis/wit/workitems?ids={ids}&fields=System.WorkItemType,System.IterationPath,Microsoft.VSTS.Scheduling.Effort,Microsoft.VSTS.Common.ClosedDate&api-version=7.0"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])


def refresh_iterations():
    """
    Fetch iteration data from Azure DevOps and store in MongoDB.
    Uses try/except around each iteration to ensure partial progress if errors occur.
    """
    try:
        iterations = get_iterations()
    except Exception as e:
        logging.error(f"Failed to fetch iterations from ADO: {e}")
        return

    for iteration in iterations:
        try:
            # Extract iteration metadata
            iteration_name = iteration["path"]
            start_date = iteration.get("attributes", {}).get("startDate")
            end_date = iteration.get("attributes", {}).get("finishDate")

            logging.info(f"Processing iteration: {iteration_name}")

            # Fetch work items for this iteration
            work_items = get_work_items_for_iteration(iteration_name)

            num_user_stories = 0
            num_bugs = 0
            sum_effort_user_story = 0
            closed_late = 0

            for wi in work_items:
                fields = wi.get("fields", {})
                w_type = fields.get("System.WorkItemType")
                effort = fields.get("Microsoft.VSTS.Scheduling.Effort")
                closed_date = fields.get("Microsoft.VSTS.Common.ClosedDate")

                if w_type == "User Story":
                    num_user_stories += 1
                    if effort:
                        sum_effort_user_story += effort

                    if closed_date and end_date:
                        closed_dt = datetime.fromisoformat(closed_date.replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                        if closed_dt > end_dt:
                            closed_late += 1

                elif w_type == "Bug":
                    num_bugs += 1

            # Prepare iteration document
            iteration_doc = {
                "IterationName": iteration_name,
                "IterationStartDate": start_date,
                "IterationEndDate": end_date,
                "NumberOfUserStories": num_user_stories,
                "NumberOfBugs": num_bugs,
                "SumEffortUserStory": sum_effort_user_story,
                "OnTime": closed_late,
            }

            # Upsert into MongoDB (no duplicates by IterationName)
            collection.update_one(
                {"IterationName": iteration_name},
                {"$set": iteration_doc},
                upsert=True
            )

            logging.info(f"Iteration data stored: {iteration_name}")

        except Exception as e:
            # Log the failure but continue with other iterations
            logging.error(f"Failed to process iteration {iteration.get('path', 'UNKNOWN')}: {e}")

    logging.info("Iteration data refresh complete.")
