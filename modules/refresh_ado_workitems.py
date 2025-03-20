def refresh_work_items(fetch_only=False):  # Add parameter
    ...
    all_work_items = []
    
    for i in range(0, len(work_item_ids), batch_size):
        batch = work_item_ids[i:i + batch_size]
        response = wit_client.get_work_items(batch, expand='All')

        if not response:
            break

        for work_item in response:
            all_work_items.append(work_item.fields)

    if fetch_only:
        return all_work_items  # Return data instead of storing it
    ...
