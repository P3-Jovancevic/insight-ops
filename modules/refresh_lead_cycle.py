from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient, UpdateOne
from azure.devops.v7_0.work.models import TeamContext
from datetime import datetime
import traceback

def refresh_lead_cycle():
    # Load secrets
    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = st.secrets["ado"].get("organization_url", "https://dev.azure.com/p3ds/")
    project_name = st.secrets["ado"].get("project_name", "P3-Tech-Master")
    team_name = st.secrets["ado"].get("team_name", "P3-Tech-Master Team")
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    # Connect to Azure DevOps
    credentials = BasicAuthentication('', personal_access_token)
    connection = Connection(base_url=organization_url, creds=credentials)
    wit_client = connection.clients.get_work_item_tracking_client()
    team_client = connection.clients.get_work_client()

    # Connect to MongoDB
    with MongoClient(mongo_uri) as client:
        db = client[db_name]
        collection = db["lead-cycle-data"]

        # Fetch iteration details
        iteration_dates = {}
        try:
            team_context = TeamContext(project=project_name, team=team_name)
            iterations = team_client.get_team_iterations(team_context)
            for iteration in iterations:
                iteration_dates[iteration.path] = {
                    "IterationStartDate": iteration.attributes.start_date,
                    "IterationEndDate": iteration.attributes.finish_date
                }
        except Exception as e:
            st.error(f"Failed to fetch iteration dates: {e}")
            st.error(traceback.format_exc())
            return

        # Define WIQL query to get Lead and Cycle Time data
        wiql_query = {
            "query": f"""
                SELECT [System.Id], [System.IterationPath], [System.CreatedDate],
                       [Microsoft.VSTS.Common.ActivatedDate], [Microsoft.VSTS.Common.ClosedDate]
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
                st.warning("No data found.")
                return

            batch_size = 200
            iteration_data = []

            for i in range(0, len(work_item_ids), batch_size):
                batch = work_item_ids[i:i + batch_size]
                response = wit_client.get_work_items(batch, expand='All')

                if not response:
                    continue

                for work_item in response:
                    fields = work_item.fields
                    iteration = fields.get("System.IterationPath", "Unknown").strip()
                    created_date = fields.get("System.CreatedDate")
                    activated_date = fields.get("Microsoft.VSTS.Common.ActivatedDate")
                    closed_date = fields.get("Microsoft.VSTS.Common.ClosedDate")
                    
                    if not closed_date:
                        continue  # Skip work items that are not completed
                    
                    created_date = datetime.fromisoformat(created_date) if created_date else None
                    activated_date = datetime.fromisoformat(activated_date) if activated_date else None
                    closed_date = datetime.fromisoformat(closed_date) if closed_date else None
                    
                    lead_time = (closed_date - created_date).days if created_date and closed_date else None
                    cycle_time = (closed_date - activated_date).days if activated_date and closed_date else None
                    
                    iteration_data.append({
                        "Iteration": iteration,
                        "Date": closed_date,
                        "LeadTime": float(lead_time) if lead_time is not None else None,
                        "CycleTime": float(cycle_time) if cycle_time is not None else None
                    })
            
            # Insert or update data in MongoDB
            bulk_operations = [
                UpdateOne(
                    {"Iteration": data["Iteration"], "Date": data["Date"]},
                    {"$set": data},
                    upsert=True
                ) for data in iteration_data
            ]
            
            if bulk_operations:
                collection.bulk_write(bulk_operations)
            
            st.success(f"Lead & Cycle Time data updated for {len(iteration_data)} work items.")
        
        except Exception as e:
            st.error(f"Error fetching or storing lead & cycle time data: {e}")
            st.text(f"WIQL Query: {wiql_query}")  # Debugging
            st.error(traceback.format_exc())
            
        finally:
            client.close()  # Ensure MongoDB connection is closed
