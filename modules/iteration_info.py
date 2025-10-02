from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient, ASCENDING
import traceback

def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d

def get_iterations():
    """Fetch iterations from Azure DevOps and store them in MongoDB, including Iteration ID."""
    try:
        # Get user settings from session state
        user_email = st.session_state.get("user_email")
        if not user_email:
            st.error("User not logged in.")
            return

        client = MongoClient(st.secrets["mongo"]["url"])
        db = client[st.secrets["mongo"]["db"]]
        users_collection = db["users"]

        # Get user data
        user_data = users_collection.find_one({"email": user_email})
        if not user_data:
            st.error("User data not found in database.")
            return

        # Extract settings
        organization_url = user_data.get("organization_url")
        project_name = user_data.get("project_name")
        pat = user_data.get("pat")

        if not organization_url or not project_name or not pat:
            st.error("Missing ADO configuration in user settings.")
            return

        # Connect to Azure DevOps
        credentials = BasicAuthentication("", pat)
        connection = Connection(base_url=organization_url, creds=credentials)
        core_client = connection.clients.get_core_client()

        # Fetch iterations
        iterations = core_client.get_classification_node(
            project=project_name,
            structure_group="iterations",
            depth=5
        )

        # Prepare MongoDB collection
        iterations_collection = db["iterations"]
        iterations_collection.create_index([("ADO Iteration ID", ASCENDING)], unique=True)

        def process_node(node, path=""):
            """Recursively process iteration nodes and save them with Iteration ID."""
            current_path = f"{path}/{node.name}" if path else node.name

            iteration_doc = {
                "ADO Iteration ID": node.id,   # Unique ADO Iteration ID
                "IterationName": current_path,
            }

            sanitized_doc = sanitize_keys(iteration_doc)

            # Upsert into MongoDB
            iterations_collection.update_one(
                {"ADO Iteration ID": node.id},
                {"$set": sanitized_doc},
                upsert=True
            )

            # Recurse into children
            for child in getattr(node, "children", []):
                process_node(child, current_path)

        process_node(iterations)
        st.success("Iterations (with IDs) fetched and stored successfully!")

    except Exception as e:
        st.error(f"Error fetching iterations: {str(e)}")
        traceback.print_exc()
