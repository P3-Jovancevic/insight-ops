def refresh_iterations():
    """
    Fetch iteration data from Azure DevOps and store in MongoDB.
    Stores both GUID IterationId and numeric System_IterationID, upserts by numeric ID.
    """
    try:
        iterations = get_iterations()
        logging.info(f"Fetched {len(iterations)} iterations from Azure DevOps")
    except Exception as e:
        logging.error(f"Failed to fetch iterations from ADO: {e}")
        return

    for iteration in iterations:
        try:
            # GUID ID from iteration object
            iteration_guid = iteration.get("id") or iteration.get("attributes", {}).get("iterationId")
            iteration_path = iteration.get("path")
            start_date = iteration.get("attributes", {}).get("startDate")
            end_date = iteration.get("attributes", {}).get("finishDate")

            if not iteration_guid or not iteration_path:
                logging.warning(f"Skipping iteration with missing ID or path: {iteration}")
                continue

            logging.info(f"Processing iteration: {iteration_path}")

            # Fetch work items for this iteration (using GUID)
            work_items = get_work_items_for_iteration(iteration_guid)

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
                            logging.warning(f"Failed to parse dates for work item {wi.get('id')}: {e}")

                elif w_type == "Bug":
                    num_bugs += 1

            if numeric_iteration_id is None:
                logging.warning(f"No numeric System_IterationId found for iteration {iteration_path}, skipping upsert")
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
                "OnTime": on_time_count,
                "System_IterationID": numeric_iteration_id  # numeric ID
            }

            # Upsert by numeric System_IterationID
            collection.update_one(
                {"System_IterationID": numeric_iteration_id},
                {"$set": iteration_doc},
                upsert=True
            )

            logging.info(f"Iteration data stored: {iteration_path} (Numeric ID: {numeric_iteration_id})")

        except Exception as e:
            logging.error(f"Failed to process iteration {iteration.get('path', 'UNKNOWN')}: {e}")

    logging.info("Iteration data refresh complete.")
