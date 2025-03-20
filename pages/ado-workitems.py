import streamlit as st
from modules.refresh_ado_workitems import refresh_work_items  # Import function

st.title("Azure DevOps Work Items")

if st.button("Fetch Work Items from Azure DevOps"):
    st.write("Fetching work items... Please wait.")
    
    # Call function to fetch data
    work_items = refresh_work_items(fetch_only=True)  

    if work_items:
        st.subheader("Fetched Work Items from Azure DevOps")
        st.dataframe(work_items)  # Display work items in a table
    else:
        st.warning("No work items found.")
