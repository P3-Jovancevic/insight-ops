from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient, UpdateOne
from azure.devops.v7_0.work.models import TeamContext
from datetime import datetime
import traceback

def refresh_velocity_data():
    # Load secrets
    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = st.secrets["ado"]["ado_site"]
    project_name = st.secrets["ado"]["ado_project"]
    team_name = st.secrets["ado"]["ado_team"]
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    # Connect to Azure DevOps
    credentials = BasicAuthentication('', personal_access_token)
    connection = Connection(base_url=organization_url, creds=credentials)
    wit_client = connection.clients.get_work_item_tracking_client()
    core_client = connection.clients.get_core_client()
    team_client = connection.clients.get_work_client()

    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["velocity-data"]

    # Fetch iteration details
    iteration_dates = {}
    try:
        team_context = TeamContext(project=project_name, team=team_name)
        iterations = team_client.get_team_iterations(team_context)
        for iteration in iterations:
            iteration_dates[iteration.path] = {
                "IterationStartDate": iteration.attributes.start_date if iteration.attributes.start_date else None,
                "IterationEndDate": iteration.attributes.finish_date if iteration.attributes.finish_date else None
            }
    except Exception as e:
        st.error(f"Failed to fetch iteration dates: {e}")
        st.error(traceback.format_exc())
        return

    # Initialize iteration_data with all iterations (zeroed metrics)
    iteration_data = {}
    for iteration, dates in iteration_dates.items():
        iteration_start = dates["IterationStartDate"]
        iteration_end = dates["IterationEndDate"]

        if iteration_start and isinstance(iteration_start, str):
            iteration_start = datetime.fromisoformat(iteration_start)
        if iteration_end and isinstance(iteration_end, str):
            iteration_end = datetime.fromisoformat(iteration_end)

        iteration_data[iteration] = {
            "IterationName": iteration,
            "IterationStartDate": iteration_start,
            "IterationEndDate": iteration_end,
            "TotalUserStories": 0,
            "SumEffort": 0,
            "DoneUserStories": 0,
            "SumEffortDone": 0
        }

    # Define WIQL query to get all User Stories
    wiql_query = {
        "query": f"""
            SELECT [System.Id], [System.IterationPath], [System.State],
                   [Microsoft.VSTS.Scheduling.Effort], [Microsoft.VSTS.Common.ClosedDate]
            FROM WorkItems
            WHERE [System.TeamProject] = '{project_name}'
            AND [System.WorkItemType] = 'User Story'
        """
    }

    try:
        # Execute WIQL query
        query_results = wit_client.query_by_wiql(wiql_query)
        work_item_ids = [wi.id for wi in query_results.work_items]

        if work_item_ids:
            batch_size = 200

            for i in range(0, len(work_item_ids), batch_size):
                batch = work_item_ids[i:i + batch_size]
                response = wit_client.get_work_items(batch, expand='All')

                if not response:
                    break

                for work_item in response:
                    fields = work_item.fields
                    iteration = fields.get("System.IterationPath", "Unknown").strip()
                    state = fields.get("System.State", "").lower()
                    effort = fields.get("Microsoft.VSTS.Scheduling.Effort", 0) or 0
                    closed_date = fields.get("Microsoft.VSTS.Common.ClosedDate", None)

                    iteration_end = iteration_data.get(iteration, {}).get("IterationEndDate")

                    # Convert closed_date to datetime
                    if closed_date and isinstance(closed_date, str):
                        closed_date = datetime.fromisoformat(closed_date)

                    # Increment totals
                    if iteration in iteration_data:
                        iteration_data[iteration]["TotalUserStories"] += 1
                        iteration_data[iteration]["SumEffort"] += effort

                        # Count as done only if state is "Done" AND ClosedDate <= IterationEndDate
                        if state == "done" and closed_date and iteration_end and closed_date <= iteration_end:
                            iteration_data[iteration]["DoneUserStories"] += 1
                            iteration_data[iteration]["SumEffortDone"] += effort

        # Bulk upsert all iterations into MongoDB
        bulk_operations = [
            UpdateOne(
                {"IterationName": data["IterationName"]},
                {"$set": data},
                upsert=True
            ) for data in iteration_data.values()
        ]

        if bulk_operations:
            collection.bulk_write(bulk_operations)

        st.success(f"Velocity data updated for {len(iteration_data)} iterations.")

    except Exception as e:
        st.error(f"Error fetching or storing velocity data: {e}")
        st.text(f"WIQL Query: {wiql_query}")  # Show query for debugging
        st.error(traceback.format_exc())

    finally:
        client.close()
