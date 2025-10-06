from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
from datetime import datetime
import traceback

# --------------------------------------------------------
# Helper function
# --------------------------------------------------------
def sanitize_keys(d):
    """Replace invalid MongoDB characters ('.' and '$') in JSON keys."""
    if isinstance(d, dict):
        return {k.replace(".", "_").replace("$", "_"): sanitize_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [sanitize_keys(i) for i in d]
    else:
        return d

# --------------------------------------------------------
# Main refresh function
# --------------------------------------------------------
def refresh_iterations():
    # Load secrets
    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = st.secrets["ado"]["ado_site"]
    project_name = st.secrets["ado"]["ado_project"]
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    try:
        # --------------------------------------------------------
        # Connect to Azure DevOps
        # --------------------------------------------------------
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        wit_client = connection.clients.get_work_item_tracking_client()
        work_client = connection.clients.get_work_client()

        # --------------------------------------------------------
        # Connect to MongoDB
        # --------------------------------------------------------
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db["iteration-data"]

        # --------------------------------------------------------
        # Get all iterations (including dates and paths)
        # --------------------------------------------------------
        st.info("Fetching iterations from Azure DevOps...")

        iterations = work_client.get_team_iterations(project=project_name, team=project_name)
        if not iterations:
            st.warning("No iterations found.")
            return

        st.info(f"Found {len(iterations)} iterations.")

        # --------------------------------------------------------
        # Process each iteration
        # --------------------------------------------------------
        for iteration in iterations:
            iteration_id = iteration.id
            iteration_path = iteration.path
            start_date = getattr(iteration.attributes, "start_date", None)
            end_date = getattr(iteration.attributes, "finish_date", None)

            # Format to datetime if available
            start_date = datetime.fromisoformat(start_date.replace("Z", "")) if start_date else None
            end_date = datetime.fromisoformat(end_date.replace("Z", "")) if end_date else None

            # --------------------------------------------------------
            # Fetch Work Items for this iteration
            # --------------------------------------------------------
            wiql = {
                "query": f"""
                    SELECT [System.Id], [System.WorkItemType], [System.State],
                           [Microsoft.VSTS.Scheduling.Effort], [Microsoft.VSTS.Common.ClosedDate]
                    FROM WorkItems
                    WHERE [System.IterationPath] = '{iteration_path}'
                """
            }

            query_result = wit_client.query_by_wiql(wiql).work_items
            if not query_result:
                iteration_data = {
                    "IterationID": iteration_id,
                    "IterationPath": iteration_path,
                    "IterationStartDate": start_date,
                    "IterationEndDate": end_date,
                    "NumberOfUserStories": 0,
                    "NumberOfBugs": 0,
                    "SumEffortUserStories": 0,
                    "NumberOfStoriesDone": 0,
                    "NumberOfStoriesLate": 0
                }
                collection.update_one({"IterationID": iteration_id}, {"$set": iteration_data}, upsert=True)
                continue

            # Get detailed work item info in batches
            work_item_ids = [wi.id for wi in query_result]
            batch_size = 200
            all_items = []

            for i in range(0, len(work_item_ids), batch_size):
                batch = work_item_ids[i:i + batch_size]
                details = wit_client.get_work_items(batch, expand="All")
                all_items.extend(details)

            # --------------------------------------------------------
            # Aggregate metrics
            # --------------------------------------------------------
            user_stories = [wi for wi in all_items if wi.fields.get("System.WorkItemType") == "User Story"]
            bugs = [wi for wi in all_items if wi.fields.get("System.WorkItemType") == "Bug"]

            num_user_stories = len(user_stories)
            num_bugs = len(bugs)
            sum_effort = sum(
                wi.fields.get("Microsoft.VSTS.Scheduling.Effort", 0) or 0
                for wi in user_stories
            )
            stories_done = [wi for wi in user_stories if wi.fields.get("System.State") == "Done"]

            # Count stories with ClosedDate > IterationEndDate
            stories_late = 0
            if end_date:
                for wi in user_stories:
                    closed_date_str = wi.fields.get("Microsoft.VSTS.Common.ClosedDate")
                    if closed_date_str:
                        try:
                            closed_date = datetime.fromisoformat(closed_date_str.replace("Z", ""))
                            if closed_date > end_date:
                                stories_late += 1
                        except Exception:
                            pass

            # --------------------------------------------------------
            # Prepare document and upsert to MongoDB
            # --------------------------------------------------------
            iteration_data = {
                "IterationID": iteration_id,
                "IterationPath": iteration_path,
                "IterationStartDate": start_date,
                "IterationEndDate": end_date,
                "NumberOfUserStories": num_user_stories,
                "NumberOfBugs": num_bugs,
                "SumEffortUserStories": sum_effort,
                "NumberOfStoriesDone": len(stories_done),
                "NumberOfStoriesLate": stories_late
            }

            collection.update_one({"IterationID": iteration_id}, {"$set": sanitize_keys(iteration_data)}, upsert=True)

        # --------------------------------------------------------
        # Finish
        # --------------------------------------------------------
        st.success("✅ Iteration data refreshed and stored in MongoDB (collection: iteration-data).")

    except Exception as e:
        st.error(f"❌ Error during iteration refresh: {e}")
        st.error(traceback.format_exc())
