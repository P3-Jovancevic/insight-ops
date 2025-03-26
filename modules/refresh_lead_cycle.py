from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
import traceback
from datetime import datetime

def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d

def calculate_time_difference(start_date, end_date):
    """Calculate the time difference in days."""
    if start_date and end_date:
        return (end_date - start_date).days
    return None

def refresh_work_items():
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
    collection = db["lead-cycle-data"]

    # Create index on System_Id to improve performance
    collection.create_index([("System_Id", 1)], unique=True)

    # Define WIQL query to get work items
    wiql_query = {
        "query": f"SELECT [System.Id], [System.CreatedDate], [System.State], [System.ChangedDate] FROM WorkItems WHERE [System.TeamProject] = '{project_name}'"
    }

    try:
        # Execute WIQL query
        work_item_ids = []
        continuation_token = None

        while True:
            if continuation_token:
                query_results = wit_client.query_by_wiql(wiql_query, continuation_token=continuation_token)
            else:
                query_results = wit_client.query_by_wiql(wiql_query)

            work_item_ids.extend([wi.id for wi in query_results.work_items])

            if not query_results.continuation_token:
                break
            continuation_token = query_results.continuation_token

        if not work_item_ids:
            st.warning("No Work Items found in project.")
            return

        st.info(f"Total Work Items found: {len(work_item_ids)}")

        batch_size = 200

        for i in range(0, len(work_item_ids), batch_size):
            batch = work_item_ids[i:i + batch_size]
            response = wit_client.get_work_items(batch, expand='All')

            if not response:
                break

            for work_item in response:
                fields = work_item.fields
                created_date = fields.get('System.CreatedDate')
                state = fields.get('System.State')
                changed_date = fields.get('System.ChangedDate')

                # Assume work items go "In Progress" and then "Done"
                start_date = None  # Set to None initially
                if state == "In Progress":
                    start_date = changed_date  # Use state change time for cycle time

                # Calculate Lead Time and Cycle Time
                lead_time = calculate_time_difference(created_date, changed_date)
                cycle_time = calculate_time_difference(start_date, changed_date) if start_date else None

                sanitized_data = sanitize_keys(fields)
                sanitized_data["System_Id"] = work_item.id  # Ensure System.Id is available
                sanitized_data["Lead_Time"] = lead_time
                sanitized_data["Cycle_Time"] = cycle_time

                # Use upsert to avoid duplicates
                collection.update_one(
                    {"System_Id": sanitized_data["System_Id"]},
                    {"$set": sanitized_data},
                    upsert=True
                )

        st.success(f"Stored or updated {len(work_item_ids)} work items in MongoDB.")
    
    except Exception as e:
        st.error(f"Error fetching or storing Work Items: {e}")
        st.error(traceback.format_exc())
