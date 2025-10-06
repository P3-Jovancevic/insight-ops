import streamlit as st
import pandas as pd
from pymongo import MongoClient
from modules.iteration_info import refresh_iterations

st.title("Azure DevOps Iterations")

# --------------------------------------------------------
# MongoDB setup
# --------------------------------------------------------
mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]
collection_name = "iteration-data"

client = MongoClient(mongo_uri)
db = client[db_name]
collection = db[collection_name]

# --------------------------------------------------------
# Refresh Iteration Data
# --------------------------------------------------------
if st.button("↻ Refresh Iterations"):
    with st.spinner("Refreshing iteration data from Azure DevOps..."):
        refresh_iterations()
    st.success("Iteration data refreshed successfully!")
    st.rerun()

# --------------------------------------------------------
# Load Iteration Data from MongoDB
# --------------------------------------------------------
def load_iterations():
    """Fetch iteration data from MongoDB."""
    iterations = list(collection.find({}, {"_id": 0}))  # Exclude internal Mongo _id
    if not iterations:
        return None, "No iteration data found. Please refresh."
    return iterations, None

iterations, error_message = load_iterations()

# --------------------------------------------------------
# Display Iteration Data
# --------------------------------------------------------
if error_message:
    st.warning(error_message)
else:
    st.write(f"**Number of iterations:** {len(iterations)}")

    # Convert to DataFrame and display
    if isinstance(iterations, list) and all(isinstance(i, dict) for i in iterations):
        df = pd.DataFrame(iterations)

        # Optional: sort by start date if available
        if "IterationStartDate" in df.columns:
            df = df.sort_values(by="IterationStartDate", ascending=True)

        st.dataframe(df, use_container_width=True)
    else:
        st.json(iterations)  # Fallback for unexpected data format
