import streamlit as st
import pandas as pd
import plotly.express as px
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
            st.rerun()
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
    st.write(f"Total Sprints: {len(work_items)}")
    
    # Convert to DataFrame
    df = pd.DataFrame(work_items)
    
    # Ensure necessary columns exist
    if {"IterationName", "SumEffort"}.issubset(df.columns):
        # Convert SumEffort to numeric (non-negative)
        df["SumEffort"] = pd.to_numeric(df["SumEffort"], errors="coerce").clip(lower=0)
        
        # Sort by IterationName for proper x-axis order
        df = df.sort_values(by="IterationName")
        
        # Create line chart
        fig = px.line(df, x="IterationName", y="SumEffort", markers=True,
                      title="Sum Effort per Iteration")
        fig.update_layout(
            yaxis=dict(range=[0, max(1, df["SumEffort"].max())], title="Sum Effort"),
            xaxis=dict(title="Iteration Name")
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Required fields 'IterationName' and 'SumEffort' are missing in the data.")
