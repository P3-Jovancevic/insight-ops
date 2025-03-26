from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
import traceback
from pymongo.errors import DuplicateKeyError

def refresh_lead_cycle():
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

    # Check if index exists before creating
    existing_indexes = collection.list_indexes()
    index_names = [index["name"] for index in existing_indexes]
    
    if "System_Id_1" not in index_names:
        # Create index only if it doesn't already exist
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
            query_results = wit_client.query_by_wiql(wiql_query, continuation_token=continuation_token)
            
            # Check if continuation_token exists in the response
            if hasattr(query_results, 'continuation_token') and query_results.continuation_token:
                continuation_token = query_results.continuation_token
            else:
                continuation_token = None  # No more pages of results, so set continuation_token to None

            work_item_ids.extend([wi.id for wi in query_results.work_items])

            # If there is no continuation_token, break the loop as we've processed all pages
            if not continuation_token:
                break

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

                try:
                    # Use upsert to avoid duplicates
                    collection.update_one(
                        {"System_Id": sanitized_data["System_Id"]},
                        {"$set": sanitized_data},
                        upsert=True
                    )
                except DuplicateKeyError:
                    st.warning(f"Duplicate entry found for work item ID {sanitized_data['System_Id']}. Skipping...")

        st.success(f"Stored or updated {len(work_item_ids)} work items in MongoDB.")
    
    except Exception as e:
        st.error(f"Error fetching or storing Work Items: {e}")
        st.error(traceback.format_exc())

def calculate_time_difference(start_date, end_date):
    from datetime import datetime

    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S.%fZ")
        return (end - start).total_seconds() / (60 * 60 * 24)  # Return in days
    return None

def sanitize_keys(data):
    # Example: Remove or rename invalid characters from keys if needed
    sanitized = {}
    for key, value in data.items():
        sanitized[key.replace(" ", "_")] = value
    return sanitized
