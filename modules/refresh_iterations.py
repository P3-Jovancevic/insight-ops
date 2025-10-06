from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import streamlit as st
from pymongo import MongoClient
from datetime import datetime
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
    # Load secrets
    personal_access_token = st.secrets["ado"]["ado_pat"]
    organization_url = st.secrets["ado"]["ado_site"]
    project_name = st.secrets["ado"]["ado_project"]
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    try:
        # Connect to Azure DevOps
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=organization_url, creds=credentials)
        wit_client = connection.clients.get_work_item_tracking_client()
        work_client = connection.clients.get_work_client()

        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db["iteration-data"]

        # --------------------------------------------------------
        # Step 1: Fetch all iteration nodes in the project
        # --------------------------------------------------------
        def traverse_iteration_nodes(node, parent_path=""):
            """Recursively traverse iteration nodes to get all paths with dates."""
            iteration_list = []
            current_path = f"{parent_path}\\{node.name}" if parent_path else node.name
            start_date = getattr(node.attributes, "start_date", None)
            end_date = getattr(node.attributes, "finish_date", None)

            iteration_list.append({
                "IterationPath": current_path,
                "StartDate": start_date,
                "EndDate": end_date
            })

            # Recurse into child nodes
            children = getattr(node, "children", [])
            for child in children:
                iteration_list.extend(traverse_iteration_nodes(child, current_path))

            return iteration_list

        # Get top-level iteration node
        root_node = work_client.get_classification_node(
            project=project_name,
            structure_group="iterations",
            depth=10
        )

        all_iterations = traverse_iteration_nodes(root_node)
        st.write(f"Found {len(all_iterations)} iteration paths.")

        # --------------------------------------------------------
        # Step 2: For each iteration, fetch work items and compute metrics
        # --------------------------------------------------------
        for iteration in all_iterations:
            iteration_path = iteration["IterationPath"]
            start_date_str = iteration["StartDate"]
            end_date_str = iteration["EndDate"]

            try:
                start_date = datetime.fromisoformat(start_date_str.replace("Z", "")) if start_date_str else None
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "")) if end_date_str else None
            except Exception:
                start_date = None
                end_date = None

            # WIQL query
            wiql = {
                "query": f"""
                    SELECT [System.Id], [System.WorkItemType], [System.State],
                           [Microsoft.VSTS.Scheduling.Effort], [Microsoft.VSTS.Common.ClosedDate]
                    FROM WorkItems
                    WHERE [System.IterationPath] = '{iteration_path}'
                """
            }

            query_result = wit_client.query_by_wiql(wiql).work_items
            work_items = []
            if query_result:
                ids = [wi.id for wi in query_result]
                batch_size = 200
                for i in range(0, len(ids), batch_size):
                    batch = ids[i:i + batch_size]
                    work_items.extend(wit_client.get_work_items(batch, expand="All"))

            # Metrics
            user_stories = [wi for wi in work_items if wi.fields.get("System.WorkItemType") == "User Story"]
            bugs = [wi for wi in work_items if wi.fields.get("System.WorkItemType") == "Bug"]

            num_user_stories = len(user_stories)
            num_bugs = len(bugs)
            sum_effort = sum(wi.fields.get("Microsoft.VSTS.Scheduling.Effort", 0) or 0 for wi in user_stories)
            stories_done = [wi for wi in user_stories if wi.fields.get("System.State") == "Done"]

            # Late stories
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

            # Document for Mongo
            iteration_data = {
                "IterationID": getattr(iteration, "id", None),
                "IterationPath": iteration_path,
                "IterationStartDate": start_date,
                "IterationEndDate": end_date,
                "NumberOfUserStories": num_user_stories,
                "NumberOfBugs": num_bugs,
                "SumEffortUserStories": sum_effort,
                "NumberOfStoriesDone": len(stories_done),
                "NumberOfStoriesLate": stories_late
            }

            # Upsert
            collection.update_one(
                {"IterationPath": iteration_path},
                {"$set": sanitize_keys(iteration_data)},
                upsert=True
            )

            st.write(f"Inserted/Updated iteration: {iteration_path} | User Stories: {num_user_stories}, Bugs: {num_bugs}")

        st.success("✅ All iteration data refreshed and stored in MongoDB.")

    except Exception as e:
        st.error(f"❌ Error refreshing iterations: {e}")
        st.error(traceback.format_exc())
