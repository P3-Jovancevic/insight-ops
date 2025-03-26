import streamlit as st
import pandas as pd
from pymongo import MongoClient
from modules.refresh_velocity_data import refresh_velocity_data

st.title("Azure DevOps Velocity")

# Load MongoDB credentials from Streamlit secrets
try:
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]
    collection_name = "velocity-data"

    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
except Exception as e:
    st.error(f"Failed to connect to MongoDB: {e}")
    st.stop()  # Stop execution if connection fails

# Button to refresh work items
if st.button("↻ Refresh"):
    with st.spinner("Refreshing velocity data..."):
        try:
            refresh_velocity_data()  # Fetch and store data in MongoDB
            st.success("Velocity data refreshed successfully!")
            st.rerun()  # Reload page after refresh
        except Exception as e:
            st.error(f"Failed to refresh velocity data: {e}")

# Load and display work items from MongoDB
def load_work_items():
    """Fetch work items from MongoDB."""
    try:
        work_items = list(collection.find({}, {"_id": 0}))  # Exclude MongoDB's _id field
        if not work_items:
            return None, "No work items found in MongoDB. Please refresh."
        return work_items, None
    except Exception as e:
        return None, f"Error loading work items: {e}"

work_items, error_message = load_work_items()

if error_message:
    st.warning(error_message)
else:
    st.write(f"Total Work Items: {len(work_items)}")

    # Convert to DataFrame and handle nested structures
    if isinstance(work_items, list) and all(isinstance(i, dict) for i in work_items):
        df = pd.DataFrame(work_items)
        
        # Convert any list or dict columns into JSON strings for better display
        for col in df.columns:
            if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
                df[col] = df[col].apply(lambda x: str(x))  # Convert to string format
        
        st.dataframe(df)
    else:
        st.json(work_items)  # Fallback to JSON display
