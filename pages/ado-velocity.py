import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient
from modules.refresh_velocity_data import refresh_velocity_data
from datetime import datetime, timedelta

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

        # Add a calendar date picker for filtering (start and end dates)
        min_date = df["IterationEndDate"].min().date()
        max_date = df["IterationEndDate"].max().date()

        # Calculate the default date range for the last 2 months
        end_date_default = datetime.today().date()  # Today's date
        start_date_default = end_date_default - timedelta(days=60)  # 60 days ago (approx 2 months)

        # If the calculated start date is earlier than the minimum date in the data, use the minimum date instead
        start_date_default = max(start_date_default, min_date)

        # Set the date inputs to the last 2 months as default (convert datetime to date)
        start_date = st.date_input("Select start date", min_value=min_date, max_value=max_date, value=start_date_default)
        end_date = st.date_input("Select end date", min_value=min_date, max_value=max_date, value=end_date_default)

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
