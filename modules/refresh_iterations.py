from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
from datetime import datetime
import traceback

def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d

def refresh_iterations_basic():
    """
    Fetch all iteration paths and their start/end dates from Azure DevOps
    and store them in MongoDB. Displays status messages on Streamlit page.
    """
    # Load secrets
    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = st.secrets["ado"]["ado_site"]
    project_name = st.secrets["ado"]["ado_project"]
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    try:
        st.info("Connecting to Azure DevOps...")
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        work_client = connection.clients.get_work_client()
        st.success("Connected to Azure DevOps.")

        st.info("Connecting to MongoDB...")
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db["iteration-data"]
        st.success("Connected to MongoDB.")

        st.info("Fetching iteration nodes...")
        root_node = work_client.get_classification_node(
            project=project_name,
            structure_group="iterations",
            depth=10
        )

        def traverse_nodes(node, parent_path=""):
            iteration_list = []
            path = f"{parent_path}\\{node.name}" if parent_path else node.name
            start_date = getattr(node.attributes, "start_date", None)
            end_date = getattr(node.attributes, "finish_date", None)

            iteration_list.append({
                "IterationPath": path,
                "IterationStartDate": start_date,
                "IterationEndDate": end_date
            })

            children = getattr(node, "children", [])
            for child in children:
                iteration_list.extend(traverse_nodes(child, path))

            return iteration_list

        iterations = traverse_nodes(root_node)
        st.write(f"Found {len(iterations)} iterations.")

        if not iterations:
            st.warning("No iterations found. Check if iterations exist in Azure DevOps project.")
            return

        st.info("Storing iterations into MongoDB...")
        for iteration in iterations:
            collection.update_one(
                {"IterationPath": iteration["IterationPath"]},
                {"$set": sanitize_keys(iteration)},
                upsert=True
            )
            st.write(f"Inserted/Updated iteration: {iteration['IterationPath']}")

        st.success("✅ Iteration paths stored in MongoDB successfully.")

    except Exception as e:
        st.error(f"Error fetching iteration paths: {e}")
        st.error(traceback.format_exc())
