import streamlit as st
import pymongo
import bcrypt
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth

# MongoDB connection setup
MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None

if not st.session_state["logged_in"]:
    st.error("You are not logged in. Go to login page.")
    st.stop()

user_email = st.session_state["user_email"]
user_query = {"email": user_email.lower()}

user_doc = users_collection.find_one(user_query)

if not user_doc:
    st.error("User not found in the database.")
    st.stop()

st.subheader(f"User {user_email} is logged in")
st.markdown("### Edit Your Profile")

def validate_pat(org_url, project, pat):
    """Try to access the Azure DevOps Projects API to validate PAT and access."""
    try:
        org = org_url.rstrip("/").split("/")[-1]
        url = f"https://dev.azure.com/{org}/{project}/_apis/projects?api-version=6.0"
        response = requests.get(url, auth=HTTPBasicAuth("", pat))
        return response.status_code == 200
    except Exception as e:
        return False

with st.form("update_profile_form"):
    org_url = st.text_input("Organization URL", user_doc.get("organization_url", ""))
    project_name = st.text_input("Project Name", user_doc.get("project_name", ""))
    
    with st.expander("🔐 Update Personal Access Token (PAT)"):
        pat = st.text_input("Personal Access Token", user_doc.get("pat", ""), type="password")

    username = st.text_input("Username", user_doc.get("username", ""))
    submit_button = st.form_submit_button("Save Changes")

if submit_button:
    if not org_url or not project_name or not pat:
        st.warning("You need to provide the Organization URL, Project Name, and PAT.")
    else:
        # Validate PAT
        with st.spinner("Validating Azure DevOps PAT..."):
            if not validate_pat(org_url, project_name, pat):
                st.error("PAT validation failed. Check your Org URL, Project, and PAT.")
                st.stop()

        updates = {}
        if org_url != user_doc.get("organization_url", ""):
            updates["organization_url"] = org_url
        if project_name != user_doc.get("project_name", ""):
            updates["project_name"] = project_name
        if pat != user_doc.get("pat", ""):
            updates["pat"] = pat
        if username != user_doc.get("username", ""):
            updates["username"] = username

        if updates:
            updates["updated_at"] = datetime.utcnow()
            with st.spinner("Updating profile..."):
                users_collection.update_one(user_query, {"$set": updates})
            st.success("Profile updated successfully!")
            st.rerun()
        else:
            st.info("No changes were made.")

st.markdown("---")

with st.expander("🔒 Reset Password"):
    with st.form("reset_password_form"):
        new_password = st.text_input("New password", type="password")
        confirm_password = st.text_input("Confirm new password", type="password")
        reset_button = st.form_submit_button("Reset Password")

    if reset_button:
        if not new_password or not confirm_password:
            st.error("All fields are required!")
        elif new_password != confirm_password:
            st.warning("Passwords do not match!")
        else:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            with st.spinner("Updating password..."):
                users_collection.update_one(
                    user_query,
                    {
                        "$set": {"password": hashed_password, "updated_at": datetime.utcnow()},
                        "$unset": {"verification_token": ""}
                    }
                )
            st.success("Password successfully changed!")
            st.rerun()

with st.expander("⚠️ Delete Account"):
    st.error("This action is irreversible.")
    confirm_email = st.text_input("Type your email to confirm account deletion")

    if st.button("Delete My Account"):
        if confirm_email.lower() == user_email.lower():
            users_collection.delete_one(user_query)
            st.success("Account deleted.")
            st.session_state["logged_in"] = False
            st.session_state["user_email"] = None
            st.rerun()
        else:
            st.warning("Confirmation email does not match. Account not deleted.")

if st.button("Log out"):
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None
    st.success("Logged out successfully.")
    st.rerun()
