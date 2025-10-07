from azure.devops.connection import Connection
from azure.devops.v7_0.work.models import TeamContext
from msrest.authentication import BasicAuthentication
from pymongo import MongoClient
import streamlit as st
import traceback
from datetime import datetime

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
        wit_client = connection.clients.get_work_item_tracking_client()

        # Build team context
        team_context = TeamContext(project_id=project_name, team_id=team_name)

        # Connect to MongoDB
        st.info("⚙️ Connecting to MongoDB...")
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection_iterations = db["ado-iterations"]
        collection_workitems = db["ado-workitems"]

        # Fetch iterations
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
                    # Do NOT include ClosedDate here — we calculate late stories from MongoDB
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
                # Match work items for this iteration path and User Story type
                query = {
                    "System_IterationPath": iteration_path,
                    "System_WorkItemType": "User Story",
                    "Microsoft_VSTS_Common_ClosedDate": {"$ne": None}
                }
                work_items_for_iteration = list(collection_workitems.find(query, {"Microsoft_VSTS_Common_ClosedDate": 1}))
                for wi in work_items_for_iteration:
                    closed_date = wi.get("Microsoft_VSTS_Common_ClosedDate")
                    if closed_date:
                        # Convert to datetime if it's stored as string
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
                "numUserStoriesClosedLate": num_closed_late
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
