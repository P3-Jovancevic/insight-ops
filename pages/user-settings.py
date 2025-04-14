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
        st.markdown("### Edit Your Profile")

        # Editable fields
        username = st.text_input("Username", user_doc.get("username", ""))
        org_url = st.text_input("Organization URL", user_doc.get("organization_url", ""))
        project_name = st.text_input("Project Name", user_doc.get("project_name", ""))
        pat = st.text_input("Personal Access Token (PAT)", user_doc.get("pat", ""), type="password")

        if st.button("Update Profile"):
            update_result = users_collection.update_one(
                {"email": user_email.lower()},
                {
                    "$set": {
                        "username": username,
                        "organization_url": org_url,
                        "project_name": project_name,
                        "pat": pat
                    }
                }
            )
            if update_result.modified_count > 0:
                st.success("Profile updated successfully!")
                st.rerun()
            else:
                st.info("No changes were made.")

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
