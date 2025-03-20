import streamlit as st
from modules.refresh_ado_workitems import refresh_work_items

st.title("Azure DevOps Work Items")

if st.button("Fetch Work Items from Azure DevOps"):
    st.write("Fetching work items... Please wait.")

    work_items = refresh_work_items(fetch_only=True)  # Fetch directly

    if work_items:
        st.subheader("Fetched Work Items from Azure DevOps")
        st.dataframe(work_items)  # Show data in a table
    else:
        st.warning("No work items found.")
