import json
from pymongo import MongoClient
import streamlit as st
import os

def store_work_items():
    
    # Load MongoDB credentials from Streamlit secrets
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]
    collection_name = "ado-workitems"
    json_file = "work_items.json"
    
    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    
    # Check if JSON file exists
    if not os.path.exists(json_file):
        print("No work_items.json file found.")
        return
    
    # Read JSON file
    with open(json_file, "r", encoding="utf-8") as file:
        work_items = json.load(file)
    
    if not work_items:
        print("JSON file is empty. No data to store.")
        return
    
    # Insert or update work items in the database
    for item in work_items:
        if "System.Id" in item:
            collection.update_one({"System.Id": item["System.Id"]}, {"$set": item}, upsert=True)
        else:
            print("Skipping item without 'System.Id'")
    
    print(f"Stored {len(work_items)} work items in MongoDB collection '{collection_name}'")