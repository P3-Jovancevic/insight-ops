import streamlit as st
import json
import os
import pandas as pd
from modules.refresh_ado_workitems import refresh_work_items

st.title("Azure DevOps Work Items")

json_file_path = "work_items.json"

# Button to refresh work items
if st.button("Refresh Work Items"):
    refresh_work_items()  # Run the script to fetch new data
    st.success("Work items refreshed successfully!")
    st.rerun()  # Reload the app to show new data

# Display JSON data if available
def load_work_items():
    """Load work items from JSON file, handling errors gracefully."""
    if not os.path.exists(json_file_path):
        return None, "Work items data not found. Please refresh to fetch data."
    
    try:
        with open(json_file_path, "r", encoding="utf-8") as json_file:
            work_items = json.load(json_file)
            if not work_items:
                return None, "No work items found in the JSON file."
            return work_items, None
    except json.JSONDecodeError:
        return None, "Error reading work items data. The file may be corrupted."

work_items, error_message = load_work_items()

if error_message:
    st.warning(error_message)
else:
    st.write(f"Total Work Items: {len(work_items)}")
    
    # Convert to DataFrame if work_items is not already a list of dicts
    if isinstance(work_items, list) and all(isinstance(i, dict) for i in work_items):
        df = pd.DataFrame(work_items)
        st.dataframe(df)
    else:
        st.json(work_items)  # Fallback to showing JSON if structure is unknown

# Button to delete the JSON file
if os.path.exists(json_file_path):
    if st.button("Delete Stored Work Items"):
        os.remove(json_file_path)
        st.success("Work items JSON file deleted successfully!")
        st.rerun()
