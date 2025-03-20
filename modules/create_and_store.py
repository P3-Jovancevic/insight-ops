import json
import os
import streamlit as st
from pymongo import MongoClient

def store_work_items():
    try:
        # Load MongoDB credentials from Streamlit secrets
        secrets = st.secrets.get("mongo", {})
        mongo_uri = secrets.get("uri")
        db_name = secrets.get("db_name")

        if not mongo_uri or not db_name:
            st.error("MongoDB credentials are missing in Streamlit secrets.")
            return
        
        collection_name = "ado-workitems"
        json_file = "work_items.json"

        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        # Check if JSON file exists
        if not os.path.exists(json_file):
            st.warning(f"No file named '{json_file}' found in {os.getcwd()}")
            return
        
        # Read JSON file
        with open(json_file, "r", encoding="utf-8") as file:
            work_items = json.load(file)

        if not work_items:
            st.warning("JSON file is empty. No data to store.")
            return

        # Insert or update work items in the database
        inserted_count = 0
        for item in work_items:
            if "System.Id" in item:
                collection.update_one({"System.Id": item["System.Id"]}, {"$set": item}, upsert=True)
                inserted_count += 1
            else:
                st.warning("Skipping an item without 'System.Id'")

        st.success(f"Stored {inserted_count} work items in MongoDB collection '{collection_name}'")
    
    except Exception as e:
        st.error(f"An error occurred: {e}")
