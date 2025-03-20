import streamlit as st
import json
from modules.refresh_ado_workitems import refresh_work_items

st.title("Azure DevOps Work Items")

# Button to refresh work items
if st.button("Refresh Work Items"):
    refresh_work_items()  # Run the script
    st.success("Work items refreshed successfully!")

# Try to load and display the JSON file
json_file_path = "work_items.json"

try:
    with open(json_file_path, "r", encoding="utf-8") as json_file:
        work_items = json.load(json_file)

    if work_items:
        st.write(f"Total Work Items: {len(work_items)}")
        st.dataframe(work_items)  # Display work items in a table
    else:
        st.warning("No work items found in the JSON file.")

except FileNotFoundError:
    st.error("Work items data not found. Please refresh to fetch data.")

except json.JSONDecodeError:
    st.error("Error reading work items data. The file may be corrupted.")
