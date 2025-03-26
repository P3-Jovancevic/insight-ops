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
    st.write(f"Total Work Items: {len(work_items)}")

    # Convert to DataFrame
    df = pd.DataFrame(work_items)

    # Display the table
    st.subheader("Work Items Data Table")
    st.dataframe(df)

    # Ensure the necessary columns exist
    required_columns = {"IterationName", "IterationEndDate", "DoneUserStories"}
    
    if required_columns.issubset(df.columns):
        # Remove rows where IterationEndDate is empty or null
        df = df[df["IterationEndDate"].notna() & (df["IterationEndDate"] != "")]

        # Convert IterationEndDate to datetime
        df["IterationEndDate"] = pd.to_datetime(df["IterationEndDate"], errors="coerce")

        # Drop rows where the date conversion failed (e.g., invalid date formats)
        df = df.dropna(subset=["IterationEndDate"])

        # Ensure DoneUserStories is non-negative
        df["DoneUserStories"] = pd.to_numeric(df["DoneUserStories"], errors="coerce").clip(lower=0)

        # Sort data by IterationEndDate
        df = df.sort_values(by="IterationEndDate")

        # Add a date range picker for filtering
        min_date = df["IterationEndDate"].min().date()
        max_date = df["IterationEndDate"].max().date()

        start_date, end_date = st.slider(
            "Select date range",
            min_value=min_date,
            max_value=max_date,
            value=(min_date, max_date),
            format="YYYY-MM-DD"
        )

        # Filter the DataFrame based on the selected date range
        df_filtered = df[(df["IterationEndDate"].dt.date >= start_date) & (df["IterationEndDate"].dt.date <= end_date)]

        # Create the line chart with y-axis starting at 0
        st.subheader("Done User Stories Over Iterations")
        fig = px.line(df_filtered, x="IterationName", y="DoneUserStories", 
                      title="Done User Stories Over Iterations",
                      markers=True)
        
        # Force y-axis to start at 0 and avoid negative values
        fig.update_layout(yaxis=dict(range=[0, max(1, df_filtered["DoneUserStories"].max())]))

        # Display the chart
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning(f"Required fields {required_columns} are missing.")
