import streamlit as st
import pymongo
import bcrypt
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

        # Show warning if any of the important fields are blank
        if not org_url or not project_name or not pat:
            st.warning("You need the Organization URL, your Project Name, and the PAT (Personal Access Token) in order to use InsightOps.")

        if st.button("Update project info"):
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
        
        # Divider line at the bottom
        st.markdown("---")

        if st.button("Update user"):
            update_result = users_collection.update_one(
                {"email": user_email.lower()},
                {
                    "$set": {
                        "username": username
                    }
                }
            )
            if update_result.modified_count > 0:
                st.success("Profile updated successfully!")
                st.rerun()
            else:
                st.info("No changes were made.")

        st.markdown("---")

        with st.form("reset_password_form"):
            new_password = st.text_input("New password", type="password")
            confirm_password = st.text_input("Confirm new password", type="password")
            submit_button = st.form_submit_button("Reset Password")
        
        if submit_button:
            if not new_password or not confirm_password:
                st.error("All fields are required!")
            elif new_password != confirm_password:
                st.warning("Passwords do not match!")
            else:
                # Hash new password
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # Update user password in DB and remove verification token
                users_collection.update_one(
                    {"email": user_email.lower()},
                    {"$set": {"password": hashed_password}, "$unset": {"verification_token": ""}}
                )
                
                st.success("Password successfully changed!")
    else:
        st.error("User not found in the database.")            
else:
    st.error("You are not logged in. Go to login page.")
    st.stop()