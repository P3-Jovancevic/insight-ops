from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
import traceback

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
    organization_url = 'https://dev.azure.com/gyra'
    project_name = "Antares"
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

        st.info(f"Total Work Items found: {len(work_item_ids)}")

        batch_size = 200

        for i in range(0, len(work_item_ids), batch_size):
            batch = work_item_ids[i:i + batch_size]
            response = wit_client.get_work_items(batch, expand='All')

            if not response:
                break

            for work_item in response:
                sanitized_data = sanitize_keys(work_item.fields)
                sanitized_data["System_Id"] = work_item.id  # Ensure System.Id is available

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