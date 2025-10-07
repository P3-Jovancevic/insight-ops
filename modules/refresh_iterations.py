from azure.devops.connection import Connection
from azure.devops.v5_1.work.models import TeamContext
from msrest.authentication import BasicAuthentication
from pymongo import MongoClient
import streamlit as st
import traceback

def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d


def refresh_iterations():
    """Fetch iteration (sprint) data from Azure DevOps and store in MongoDB."""
    try:
        st.info("🔄 Connecting to Azure DevOps...")

        # Load secrets
        personal_access_token = st.secrets["ado"]["ado_pat"]
        organization_url = st.secrets["ado"]["ado_site"]
        project_name = st.secrets["ado"]["ado_project"]
        team_name = st.secrets["ado"].get("ado_team", project_name)
        mongo_uri = st.secrets["mongo"]["uri"]
        db_name = st.secrets["mongo"]["db_name"]

        # Connect to Azure DevOps
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        work_client = connection.clients.get_work_client()

        # Build team context (required by SDK)
        team_context = TeamContext(project_id=project_name, team_id=team_name)

        # Connect to MongoDB
        st.info("⚙️ Connecting to MongoDB...")
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db["ado-iterations"]

        # Fetch iterations
        st.info(f"📡 Fetching iterations for project '{project_name}' (team: '{team_name}')...")
        iterations = work_client.get_team_iterations(team_context)

        if not iterations:
            st.warning("No iterations found.")
            return

        st.info(f"✅ Retrieved {len(iterations)} iterations. Storing to MongoDB...")

        stored_count = 0

        for iteration in iterations:
            data = {
                "id": iteration.id,
                "name": iteration.name,
                "path": iteration.path,
                "startDate": getattr(iteration.attributes, "start_date", None),
                "finishDate": getattr(iteration.attributes, "finish_date", None)
            }

            sanitized = sanitize_keys(data)

            # Upsert into MongoDB
            collection.update_one(
                {"id": sanitized["id"]},
                {"$set": sanitized},
                upsert=True
            )
            stored_count += 1

        st.success(f"🎉 Stored or updated {stored_count} iterations in MongoDB.")

    except Exception as e:
        st.error(f"❌ Error fetching or storing iterations: {e}")
        st.error(traceback.format_exc())
