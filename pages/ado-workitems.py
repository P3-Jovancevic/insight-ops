import streamlit as st
import importlib

st.set_page_config(page_title="Your ADO work items", layout="wide")

st.title("Your ADO work items")

if st.button("Refresh work items list"):
    with st.status("Refreshing work items, please wait..."):
        try:
            refresh_ado_workitems = importlib.import_module("modules.refresh_ado_workitems")
            refresh_ado_workitems.refresh_work_items()  # Call the function correctly
            st.success("Work items refreshed successfully!")
        except Exception as e:
            st.error(f"Error refreshing work items: {e}")

# Placeholder for work items table
st.write("(Table will be displayed here)")
