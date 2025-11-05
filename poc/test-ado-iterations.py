import streamlit as st
import pandas as pd
from pymongo import MongoClient
from modules.refresh_iterations import refresh_iterations  # updated import

st.title("Azure DevOps Iterations")

# Load MongoDB credentials from Streamlit secrets
mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]
collection_name = "ado-iterations"  # updated collection name

# Connect to MongoDB
client = MongoClient(mongo_uri)
db = client[db_name]
collection = db[collection_name]

# Button to refresh iteration data
if st.button("↻ Refresh Iterations"):
    refresh_iterations()  # Fetch and store iteration data directly in MongoDB
    st.success("Iterations refreshed successfully!")
    st.rerun()

# Load and display iterations from MongoDB
def load_iterations():
    """Fetch iteration data from MongoDB."""
    iterations = list(collection.find({}, {"_id": 0}))  # Exclude MongoDB's _id field
    if not iterations:
        return None, "No iterations found in MongoDB. Please refresh."
    return iterations, None

iterations, error_message = load_iterations()

if error_message:
    st.warning(error_message)
else:
    st.write(f"Total Iterations: {len(iterations)}")

    # Convert to DataFrame and display
    if isinstance(iterations, list) and all(isinstance(i, dict) for i in iterations):
        df = pd.DataFrame(iterations)

        # Optional: order columns for readability
        preferred_order = ["name", "path", "startDate", "finishDate", "id"]
        df = df[[col for col in preferred_order if col in df.columns] + 
                [col for col in df.columns if col not in preferred_order]]

        st.dataframe(df)
    else:
        st.json(iterations)  # Fallback to JSON display
