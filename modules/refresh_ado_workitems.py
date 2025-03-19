import secrets  # Import PAT from secrets
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from pymongo import MongoClient
import json
import streamlit as st

personal_access_token = st.secrets["ado"]["ado_pat"]
organization_url = 'https://dev.azure.com/p3ds/'
project_name = "P3-Tech-Master"
mongo_uri = st.secrets["mongo"]["uri"]  # MongoDB connection string
db_name = st.secrets["mongo"]["db_name"]  # Database name

credentials = BasicAuthentication('AzureDevOps', personal_access_token)
connection = Connection(base_url=organization_url, creds=credentials)
wit_client = connection.clients.get_work_item_tracking_client()

wiql_query = {
    "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project_name}'"
}

try:
    query_results = wit_client.query_by_wiql(wiql_query)
    work_item_ids = [wi.id for wi in query_results.work_items]

    if work_item_ids:
        print(f"Total Work Items found: {len(work_item_ids)}")
        batch_size = 200
        all_work_items = []
        
        for i in range(0, len(work_item_ids), batch_size):
            batch = work_item_ids[i:i + batch_size]
            response = wit_client.get_work_items(batch, expand='All')

            if not response:
                break

            for work_item in response:
                all_work_items.append(work_item.fields)

        # Debug log: Check retrieved data
        print(f"Sample retrieved work item: {json.dumps(all_work_items[0], indent=4) if all_work_items else 'No data'}")

        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection_name = f"{project_name}-ado-workitems"
        collection = db[collection_name]

        for item in all_work_items:
            result = collection.update_one({"System.Id": item.get("System.Id")}, {"$set": item}, upsert=True)
            print(f"Upserted document with System.Id {item.get('System.Id')}: {result.matched_count} matched, {result.upserted_id} inserted")

        print(f"Total Work Items stored in MongoDB: {collection.count_documents({})}")

    else:
        print("No Work Items found in project.")

except Exception as e:
    print(f"Error fetching Work Items: {e}")