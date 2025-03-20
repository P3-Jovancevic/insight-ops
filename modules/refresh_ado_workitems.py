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
            response = wit_client.get_work_items(batch, expand='All')

            if not response:
                break

            for work_item in response:
                all_work_items.append(work_item.fields)

        # Debug log: Check retrieved data
        if all_work_items:
            print(f"Sample retrieved work item: {json.dumps(all_work_items[0], indent=4)}")

        if fetch_only:
            return all_work_items  # Return data for direct display

        # Continue with MongoDB storage if not fetching only
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection_name = f"{project_name}-ado-workitems"
        collection = db[collection_name]

        for item in all_work_items:
            if "System.Id" in item:
                collection.update_one({"System.Id": item["System.Id"]}, {"$set": item}, upsert=True)

        print(f"Total Work Items stored in MongoDB: {collection.count_documents({})}")

    except Exception as e:
        print(f"Error fetching Work Items: {e}")
        return []
