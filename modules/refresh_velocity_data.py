from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient, UpdateOne
import traceback

def refresh_velocity_data():
    # Load secrets
    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = 'https://dev.azure.com/p3ds/'
    project_name = "P3-Tech-Master"
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    # Connect to Azure DevOps
    credentials = BasicAuthentication('', personal_access_token)
    connection = Connection(base_url=organization_url, creds=credentials)
    wit_client = connection.clients.get_work_item_tracking_client()

    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db["velocity-data"]

    # Define WIQL query to get all user stories grouped by iteration
    wiql_query = {
        "query": f"""
            SELECT [System.Id], [System.IterationPath], [System.State], [Microsoft.VSTS.Scheduling.Effort], [Microsoft.VSTS.Common.ClosedDate]
            FROM WorkItems
            WHERE [System.TeamProject] = '{project_name}'
            AND [System.WorkItemType] = 'User Story'
        """
    }

    try:
        # Execute WIQL query
        query_results = wit_client.query_by_wiql(wiql_query)
        work_item_ids = [wi.id for wi in query_results.work_items]

        if not work_item_ids:
            st.warning("No User Stories found.")
            return

        st.info(f"Total User Stories found: {len(work_item_ids)}")

        batch_size = 200
        iteration_data = {}

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

                if iteration not in iteration_data:
                    iteration_data[iteration] = {
                        "IterationName": iteration,
                        "TotalUserStories": 0,
                        "DoneUserStories": 0,
                        "SumEffortDone": 0
                    }
                
                iteration_data[iteration]["TotalUserStories"] += 1
                if state == "done" and closed_date:
                    iteration_data[iteration]["DoneUserStories"] += 1
                    iteration_data[iteration]["SumEffortDone"] += effort
        
        # Insert or update data in MongoDB using bulk_write
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
        client.close()  # Ensure MongoDB connection is closed
