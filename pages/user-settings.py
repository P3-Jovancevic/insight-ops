import streamlit as st
import bcrypt
import re
from pymongo import MongoClient

# MongoDB connection (replace with your actual connection details)
client = MongoClient("your_mongo_connection_string")
db = client["your_database_name"]
users_collection = db["users"]

# Check if user is logged in
if "user_email" not in st.session_state:
    st.error("You are not logged in. Go to login page.")
    st.stop()

# Fetch user data
user_email = st.session_state["user_email"]
user_data = users_collection.find_one({"email": user_email}, {"password": 0, "verification_token": 0})

if not user_data:
    st.error("User data not found.")
    st.stop()

st.title("User Settings")

# Editable fields
organization_url = st.text_input("Organization URL", user_data.get("organization_url", ""))
project_name = st.text_input("Project Name", user_data.get("project_name", ""))
old_pat = st.text_input("Current PAT", type="password")
new_pat = st.text_input("New PAT", type="password")

# Validate URL
url_regex = re.compile(r'^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([\/\w .-]*)*\/?$')
if organization_url and not url_regex.match(organization_url):
    st.error("Invalid URL format.")

# Update logic
if st.button("Update Settings"):
    update_data = {}
    
    # Validate and hash new PAT
    if new_pat:
        stored_pat_hash = user_data.get("pat", "").encode('utf-8')
        
        if stored_pat_hash and not bcrypt.checkpw(old_pat.encode('utf-8'), stored_pat_hash):
            st.error("Incorrect current PAT.")
        else:
            new_pat_hashed = bcrypt.hashpw(new_pat.encode('utf-8'), bcrypt.gensalt())
            update_data["pat"] = new_pat_hashed.decode('utf-8')
    
    # Add other updates
    if organization_url:
        update_data["organization_url"] = organization_url
    if project_name:
        update_data["project_name"] = project_name
    
    if update_data:
        users_collection.update_one({"email": user_email}, {"$set": update_data})
        st.success("Settings updated successfully.")
        # email notification to be added
