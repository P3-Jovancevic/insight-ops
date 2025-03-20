from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import json
import secrets  # Import PAT from secrets
from pymongo import MongoClient
import streamlit as st

def refresh_work_items(fetch_only=False):

    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = 'https://dev.azure.com/p3ds/'
    project_name = "P3-Tech-Master"
    mongo_uri = st.secrets["mongo"]["uri"]  # MongoDB connection string
    db_name = st.secrets["mongo"]["db_name"]  # Database name

    # Connect to Azure DevOps
    credentials = BasicAuthentication('', personal_access_token)
    connection = Connection(base_url=organization_url, creds=credentials)

    # Get the Work Item Tracking client
    wit_client = connection.clients.get_work_item_tracking_client()

    # Define the WIQL query to fetch all Work Items in the project
    wiql_query = {
        "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project_name}'"
    }

    try:
        # Execute the WIQL query
        query_results = wit_client.query_by_wiql(wiql_query)

        # Fetch Work Item IDs
        work_item_ids = [wi.id for wi in query_results.work_items]

        if work_item_ids:
            print(f"Total Work Items found: {len(work_item_ids)}")

            batch_size = 200
            all_work_items = []
            
            for i in range(0, len(work_item_ids), batch_size):
                batch = work_item_ids[i:i + batch_size]
                response = wit_client.get_work_items(batch, expand='All')
                
                if not response:
                    break  # No more results

                for work_item in response:
                    all_work_items.append(work_item.fields)  # Store all fields

            # Save to JSON file
            with open("work_items.json", "w", encoding="utf-8") as json_file:
                json.dump(all_work_items, json_file, indent=4)

            print(f"Total Work Items retrieved and saved: {len(all_work_items)}")

        else:
            print("No Work Items found in project.")

    except Exception as e:
        print(f"Error fetching Work Items: {e}")