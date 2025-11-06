from azure.devops.connection import Connection
from azure.devops.v7_0.work.models import TeamContext
from msrest.authentication import BasicAuthentication
from pymongo import MongoClient
import streamlit as st
import traceback
from datetime import datetime
from cryptography.fernet import Fernet

def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d

def refresh_iterations():
    """Fetch iteration data and aggregated work item metrics from Azure DevOps."""
    try:
        st.info("🔄 Connecting to Azure DevOps...")

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
        client = MongoClient(MONGODB_URI)
        db = client["insightops"]
        users_collection = db["users"]
        collection_iterations = db["ado-iterations"]
        collection_workitems = db["ado-workitems"]

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
        team_name = user_doc.get("team_name", project_name)
        encrypted_pat = user_doc.get("pat", "")
        personal_access_token = decrypt_pat(encrypted_pat)

        if not all([organization_url, project_name, personal_access_token, team_name]):
            st.error("Missing Azure DevOps credentials in your profile. Please update your settings.")
            st.stop()

        # ------------------------------------------------------------------
        # Connect to Azure DevOps
        # ------------------------------------------------------------------
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        work_client = connection.clients.get_work_client()
        wit_client = connection.clients.get_work_item_tracking_client()

        # Build team context
        team_context = TeamContext(project_id=project_name, team_id=team_name)

        # ------------------------------------------------------------------
        # Fetch iterations
        # ------------------------------------------------------------------
        st.info(f"📡 Fetching iterations for project '{project_name}' (team: '{team_name}')...")
        iterations = work_client.get_team_iterations(team_context)

        if not iterations:
            st.warning("No iterations found.")
            return

        st.info(f"✅ Retrieved {len(iterations)} iterations. Fetching work items...")

        stored_count = 0

        # WIQL template: fetch IDs only
        wiql_template = """
        SELECT [System.Id], [System.WorkItemType], [System.State], [Microsoft.VSTS.Scheduling.Effort]
        FROM WorkItems
        WHERE [System.TeamProject] = '{project}'
          AND [System.IterationPath] = '{iteration_path}'
          AND [System.WorkItemType] IN ('User Story', 'Bug')
        """

        for iteration in iterations:
            iteration_path = iteration.path

            # Build WIQL for this iteration
            wiql_query = {"query": wiql_template.format(project=project_name, iteration_path=iteration_path)}

            # Execute WIQL to get work item IDs
            query_results = wit_client.query_by_wiql(wiql_query)
            work_item_ids = [wi.id for wi in query_results.work_items]

            # Initialize metrics
            num_user_stories = 0
            num_bugs = 0
            sum_effort = 0
            num_done = 0

            batch_size = 200

            for i in range(0, len(work_item_ids), batch_size):
                batch = work_item_ids[i:i + batch_size]

                # Fetch details for the batch
                response = wit_client.get_work_items(batch, fields=[
                    "System.Id",
                    "System.WorkItemType",
                    "System.State",
                    "Microsoft.VSTS.Scheduling.Effort",
                ])

                for wi in response:
                    wi_type = wi.fields.get("System.WorkItemType", "")
                    state = wi.fields.get("System.State", "")
                    effort = wi.fields.get("Microsoft.VSTS.Scheduling.Effort", 0)

                    if wi_type == "User Story":
                        num_user_stories += 1
                        sum_effort += effort if effort else 0
                        if state.lower() == "done":
                            num_done += 1
                    elif wi_type == "Bug":
                        num_bugs += 1

            # Calculate numUserStoriesClosedLate from MongoDB ado-workitems collection
            finish_date = getattr(iteration.attributes, "finish_date", None)
            num_closed_late = 0
            if finish_date:
                query = {
                    "System_IterationPath": iteration_path,
                    "System_WorkItemType": "User Story",
                    "Microsoft_VSTS_Common_ClosedDate": {"$ne": None}
                }
                work_items_for_iteration = list(collection_workitems.find(query, {"Microsoft_VSTS_Common_ClosedDate": 1}))
                for wi in work_items_for_iteration:
                    closed_date = wi.get("Microsoft_VSTS_Common_ClosedDate")
                    if closed_date:
                        if isinstance(closed_date, str):
                            closed_date = datetime.fromisoformat(closed_date.replace("Z", "+00:00"))
                        if closed_date > finish_date:
                            num_closed_late += 1

            # Build iteration document
            data = {
                "id": iteration.id,
                "name": iteration.name,
                "path": iteration.path,
                "startDate": getattr(iteration.attributes, "start_date", None),
                "finishDate": finish_date,
                "numUserStories": num_user_stories,
                "numBugs": num_bugs,
                "sumEffortUserStories": sum_effort,
                "numUserStoriesDone": num_done,
                "numUserStoriesClosedLate": num_closed_late,
                "ops_user": user_email
            }

            sanitized = sanitize_keys(data)

            # Upsert into MongoDB
            collection_iterations.update_one(
                {"id": sanitized["id"]},
                {"$set": sanitized},
                upsert=True
            )
            stored_count += 1

        st.success(f"🎉 Stored or updated {stored_count} iterations with metrics in MongoDB.")

    except Exception as e:
        st.error(f"❌ Error fetching or storing iterations: {e}")
        st.error(traceback.format_exc())
