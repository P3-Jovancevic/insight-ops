from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient

def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d

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
    collection = db["ado-workitems"]

    # Define WIQL query
    wiql_query = {
        "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project_name}'"
    }

    try:
        # Execute WIQL query
        query_results = wit_client.query_by_wiql(wiql_query)
        work_item_ids = [wi.id for wi in query_results.work_items]

        if not work_item_ids:
            st.warning("No Work Items found in project.")
            return

        print(f"Total Work Items found: {len(work_item_ids)}")

        batch_size = 200
        inserted_count = 0

        for i in range(0, len(work_item_ids), batch_size):
            batch = work_item_ids[i:i + batch_size]
            response = wit_client.get_work_items(batch, expand='All')

            if not response:
                break

            sanitized_items = []
            for work_item in response:
                sanitized_data = sanitize_keys(work_item.fields)
                sanitized_data["System_Id"] = work_item.id  # Ensure System.Id is available
                sanitized_items.append(sanitized_data)

            if sanitized_items:
                # Insert or update work items directly in MongoDB
                for item in sanitized_items:
                    collection.update_one(
                        {"System_Id": item["System_Id"]}, 
                        {"$setOnInsert": item}, 
                        upsert=True
                    )
                inserted_count += len(sanitized_items)

        st.success(f"Stored {inserted_count} work items in MongoDB.")
    
    except Exception as e:
        st.error(f"Error fetching or storing Work Items: {e}")
