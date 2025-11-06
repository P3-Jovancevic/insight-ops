import streamlit as st
import pymongo
from pymongo import MongoClient
from modules.hide_pages import hide_internal_pages

# ---------------------------------------------
# HIDE PAGES FROM NAV
# ---------------------------------------------
hide_internal_pages()

# Connect to MongoDB
MONGODB_URI = st.secrets["mongo"]["uri"]
client = pymongo.MongoClient(MONGODB_URI)
db = client["insightops"]
users_collection = db["users"]

st.set_page_config(page_title="Account Verification")

# Get token from URL
query_params = st.query_params
token = query_params.get("token")

if token:
    user = users_collection.find_one({"verification_token": token})
    
    if user:
        # Update the verified field
        users_collection.update_one(
            {"verification_token": token},
            {"$set": {"verified": True}, "$unset": {"verification_token": ""}}
        )
        
        st.success(f"User with email {user['email']} is now verified! You may now log in.")
        
        # Button to go to login page
        if st.button("Go to Login Page"):
            st.switch_page("pages/login-register.py")
    else:
        st.error("Invalid or expired verification link.")
else:
    st.error("No verification token provided.")
