import sys
import logging
from datetime import datetime

# -----------------------------
# Streamlit-safe logger setup
# -----------------------------
logger = logging.getLogger("ado_iterations")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def refresh_iterations():
    """
    Fetch iteration data from Azure DevOps and store in MongoDB.
    Stores both GUID IterationId and numeric System_IterationID, upserts by numeric ID.
    Streamlit-safe logging.
    """
    try:
        url = f"{organization_url}/{project_name}/_apis/work/teamsettings/iterations?api-version=7.0"
        logger.info(f"Fetching iterations from Azure DevOps URL: {url}")
        iterations = get_iterations()
        logger.info(f"Fetched {len(iterations)} iterations from Azure DevOps")
    except Exception:
        logger.error("Failed to fetch iterations from ADO. Check your URL, PAT, and project name.", exc_info=True)
        return

    for iteration in iterations:
        try:
            # GUID ID from iteration object
            iteration_guid = iteration.get("id") or iteration.get("attributes", {}).get("iterationId")
            iteration_path = iteration.get("path")
            start_date = iteration.get("attributes", {}).get("startDate")
            end_date = iteration.get("attributes", {}).get("finishDate")

            if not iteration_guid or not iteration_path:
                logger.warning(f"Skipping iteration with missing ID or path: {iteration}")
                continue

            logger.info(f"Processing iteration: {iteration_path} (GUID: {iteration_guid})")

            # Fetch work items for this iteration (using GUID)
            try:
                work_items = get_work_items_for_iteration(iteration_guid)
                logger.info(f"Fetched {len(work_items)} work items for iteration {iteration_path}")
            except Exception:
                logger.error(f"Failed to fetch work items for iteration {iteration_path}", exc_info=True)
                continue

            num_user_stories = 0
            num_bugs = 0
            sum_effort_user_story = 0
            on_time_count = 0
            numeric_iteration_id = None  # To be captured from work items

            for wi in work_items:
                fields = wi.get("fields", {})
                w_type = fields.get("System.WorkItemType")
                effort = fields.get("Microsoft.VSTS.Scheduling.Effort") or 0
                closed_date = fields.get("Microsoft.VSTS.Common.ClosedDate")

                # Capture numeric iteration ID from first work item
                if numeric_iteration_id is None:
                    numeric_iteration_id = fields.get("System_IterationId")

                if w_type == "User Story":
                    num_user_stories += 1
                    sum_effort_user_story += effort

                    if closed_date and end_date:
                        try:
                            closed_dt = datetime.fromisoformat(closed_date.replace("Z", "+00:00"))
                            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                            if closed_dt <= end_dt:
                                on_time_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to parse dates for work item {wi.get('id')}: {e}")

                elif w_type == "Bug":
                    num_bugs += 1

            if numeric_iteration_id is None:
                logger.warning(f"No numeric System_IterationId found for iteration {iteration_path}, skipping upsert")
                continue

            # Prepare iteration document
            iteration_doc = {
                "IterationId": iteration_guid,            # GUID
                "IterationPath": iteration_path,
                "IterationStartDate": start_date,
                "IterationEndDate": end_date,
                "NumberOfUserStories": num_user_stories,
                "NumberOfBugs": num_bugs,
                "SumEffortUserStory": sum_effort_user_story,
                "OnTime": on_time_count,                  # number of user stories completed on time
                "System_IterationID": numeric_iteration_id  # numeric ID
            }

            # Upsert by numeric System_IterationID
            collection.update_one(
                {"System_IterationID": numeric_iteration_id},
                {"$set": iteration_doc},
                upsert=True
            )

            logger.info(f"Iteration data stored: {iteration_path} (Numeric ID: {numeric_iteration_id})")

        except Exception:
            logger.error(f"Failed to process iteration {iteration.get('path', 'UNKNOWN')}", exc_info=True)

    logger.info("Iteration data refresh complete.")
