import streamlit as st
import pandas as pd
from pymongo import MongoClient
from modules.iteration_info import refresh_iterations

st.title("Azure DevOps Iterations")

# Load MongoDB credentials from Streamlit secrets
mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]
collection_name = "iteration-data"

# Connect to MongoDB
client = MongoClient(mongo_uri)
db = client[db_name]
collection = db[collection_name]

if st.button("↻ Refresh Iterations"):
    refresh_iterations()  # handles fetching iterations + work items + storing/updating Mongo
    st.success("Iteration data refreshed successfully!")
    st.rerun()

# Load and display work items from MongoDB
def load_work_items():
    """Fetch Iterations."""
    work_items = list(collection.find({}, {"_id": 0}))  # Exclude MongoDB's _id field
    if not work_items:
        return None, "No Iterations found. Please refresh."
    return work_items, None

work_items, error_message = load_work_items()

if error_message:
    st.warning(error_message)
else:
    st.write(f"Number of iterations: {len(work_items)}")

    # Convert to DataFrame and display
    if isinstance(work_items, list) and all(isinstance(i, dict) for i in work_items):
        df = pd.DataFrame(work_items)
        st.dataframe(df)
    else:
        st.json(work_items)  # Fallback to JSON display