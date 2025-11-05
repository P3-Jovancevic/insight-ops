from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
from cryptography.fernet import Fernet
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
    # ------------------------------------------------------------------
    # Verify user session
    # ------------------------------------------------------------------
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        st.error("You are not logged in. Go to the login page.")
        st.stop()

    user_email = st.session_state["user_email"]

    # ------------------------------------------------------------------
    # MongoDB connection setup
    # ------------------------------------------------------------------
    MONGODB_URI = st.secrets["mongo"]["uri"]
    DATABASE_NAME = "insightops"
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    users_collection = db["users"]
    workitems_collection = db["ado-workitems"]

    # ------------------------------------------------------------------
    # Fetch user document
    # ------------------------------------------------------------------
    user_doc = users_collection.find_one({"email": user_email.lower()})
    if not user_doc:
        st.error("User not found in the database.")
        st.stop()

    # ------------------------------------------------------------------
    # Setup Fernet decryption for PAT
    # ------------------------------------------------------------------
    FERNET_KEY = st.secrets["encryption"]["fernet_key"]
    fernet = Fernet(FERNET_KEY.encode())

    def decrypt_pat(encrypted_pat):
        try:
            return fernet.decrypt(encrypted_pat.encode()).decode()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Load user-specific ADO connection details
    # ------------------------------------------------------------------
    organization_url = user_doc.get("organization_url", "")
    project_name = user_doc.get("project_name", "")
    encrypted_pat = user_doc.get("pat", "")
    personal_access_token = decrypt_pat(encrypted_pat)

    if not all([organization_url, project_name, personal_access_token]):
        st.error("Missing Azure DevOps credentials in your profile. Please update your settings.")
        st.stop()

    # ------------------------------------------------------------------
    # Connect to Azure DevOps
    # ------------------------------------------------------------------
    try:
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        wit_client = connection.clients.get_work_item_tracking_client()
    except Exception as e:
        st.error(f"Failed to connect to Azure DevOps: {e}")
        st.stop()

    # ------------------------------------------------------------------
    # Define WIQL query
    # ------------------------------------------------------------------
    wiql_query = {
        "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project_name}'"
    }

    # ------------------------------------------------------------------
    # Fetch and store work items
    # ------------------------------------------------------------------
    try:
        query_results = wit_client.query_by_wiql(wiql_query)
        work_item_ids = [wi.id for wi in query_results.work_items]

        if not work_item_ids:
            st.warning(f"No Work Items found in project '{project_name}'.")
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
                sanitized_data["System_Id"] = work_item.id  # Ensure System.Id is present

                # Upsert to avoid duplicates
                workitems_collection.update_one(
                    {"System_Id": sanitized_data["System_Id"]},
                    {"$set": sanitized_data},
                    upsert=True
                )

        st.success(f"Stored or updated {len(work_item_ids)} work items in MongoDB.")

    except Exception as e:
        st.error(f"Error fetching or storing Work Items: {e}")
        st.error(traceback.format_exc())
