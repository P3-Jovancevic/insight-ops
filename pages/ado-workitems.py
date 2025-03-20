import streamlit as st
import pandas as pd
from pymongo import MongoClient
from modules.refresh_ado_workitems import refresh_work_items

st.title("Azure DevOps Work Items")

# Load MongoDB credentials from Streamlit secrets
mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]
collection_name = "ado-workitems"

# Connect to MongoDB
client = MongoClient(mongo_uri)
db = client[db_name]
collection = db[collection_name]

# Button to refresh work items
if st.button("Refresh Work Items"):
    refresh_work_items()  # Fetch and store data directly in MongoDB
    st.success("Work items refreshed successfully!")
    st.rerun()

# Load and display work items from MongoDB
def load_work_items():
    """Fetch work items from MongoDB."""
    work_items = list(collection.find({}, {"_id": 0}))  # Exclude MongoDB's _id field
    if not work_items:
        return None, "No work items found in MongoDB. Please refresh."
    return work_items, None

work_items, error_message = load_work_items()

if error_message:
    st.warning(error_message)
else:
    st.write(f"Total Work Items: {len(work_items)}")

    # Convert to DataFrame and display
    if isinstance(work_items, list) and all(isinstance(i, dict) for i in work_items):
        df = pd.DataFrame(work_items)
        st.dataframe(df)
    else:
        st.json(work_items)  # Fallback to JSON display
