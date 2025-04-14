import streamlit as st
import pymongo
from pymongo import MongoClient
import secrets

# MongoDB connection setup
MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

# Ensure session state keys exist
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None

# Authenticated section
if st.session_state["logged_in"]:
    user_email = st.session_state["user_email"]
    st.subheader(f"User {user_email} is logged in")

    # Fetch user document from database
    user_doc = users_collection.find_one({"email": user_email.lower()})

    if user_doc:
        st.markdown("### User Profile")
        st.text(f"Username: {user_doc.get('username', 'N/A')}")
        st.text(f"Email: {user_doc.get('email', 'N/A')}")
        st.text(f"Verified: {'✅' if user_doc.get('verified') else '❌'}")
        st.text(f"Organization URL: {user_doc.get('organization_url', 'Not set')}")
        st.text(f"Project Name: {user_doc.get('project_name', 'Not set')}")
        st.text(f"PAT: {'Set' if user_doc.get('pat') else 'Not set'}")
    else:
        st.error("User not found in the database.")

    if st.button("Sign out"):
        st.session_state["logged_in"] = False
        st.session_state["user_email"] = None
        st.rerun()

# Not authenticated
else:
    st.error("You are not logged in. Go to login page.")
    st.stop()
