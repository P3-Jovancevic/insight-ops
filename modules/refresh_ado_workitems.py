def refresh_work_items(fetch_only=False):  # Add parameter
    try:
        query_results = wit_client.query_by_wiql(wiql_query)

        if not query_results or not query_results.work_items:
            print("No work items found in the query.")
            return []  # Return empty list if nothing is found

        work_item_ids = [wi.id for wi in query_results.work_items]
        print(f"Total Work Items found: {len(work_item_ids)}")

        batch_size = 200
        all_work_items = []

        for i in range(0, len(work_item_ids), batch_size):
            batch = work_item_ids[i:i + batch_size]
            response = wit_cli
