import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient
from modules.refresh_lead_cycle import refresh_lead_cycle

st.title("Azure DevOps Lead and Cycle times")

# Load MongoDB credentials from Streamlit secrets
try:
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]
    collection_name = "lead-cycle-data"

    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
except Exception as e:
    st.error(f"Failed to connect to MongoDB: {e}")
    st.stop()  # Stop execution if connection fails

# Button to refresh data
if st.button("↻ Refresh"):
    with st.spinner("Refreshing velocity data..."):
        try:
            refresh_lead_cycle()  # Fetch and store data in MongoDB
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

    # Display the table
    st.subheader("Cycle time") # Commented out to hide the table
    st.dataframe(df) # Commented out to hide the table

    # Ensure the necessary columns exist
    required_columns = {"IterationName", "IterationEndDate", "DoneUserStories", "SumEffortDone"}
    
    if required_columns.issubset(df.columns):

        # Remove rows where IterationEndDate is empty or null
        df = df[df["IterationEndDate"].notna() & (df["IterationEndDate"] != "")]

        # Convert IterationEndDate to datetime
        df["IterationEndDate"] = pd.to_datetime(df["IterationEndDate"], errors="coerce")

        # Drop rows where the date conversion failed (e.g., invalid date formats)
        df = df.dropna(subset=["IterationEndDate"])

        # Ensure DoneUserStories and SumEffortDone are non-negative
        df["DoneUserStories"] = pd.to_numeric(df["DoneUserStories"], errors="coerce").clip(lower=0)
        df["SumEffortDone"] = pd.to_numeric(df["SumEffortDone"], errors="coerce").clip(lower=0)

        # Sort data by IterationEndDate
        df = df.sort_values(by="IterationEndDate")

        # Add a calendar date picker for filtering (start and end dates)
        min_date = df["IterationEndDate"].min().date()
        max_date = df["IterationEndDate"].max().date()

        start_date = st.date_input("Select start date", min_value=min_date, max_value=max_date, value=min_date)
        end_date = st.date_input("Select end date", min_value=min_date, max_value=max_date, value=max_date)

        # Filter the DataFrame based on the selected date range
        df_filtered = df[(df["IterationEndDate"].dt.date >= start_date) & (df["IterationEndDate"].dt.date <= end_date)]

        # Create the second line chart (Sum Effort Done)
        fig1 = px.line(df_filtered, x="IterationName", y="SumEffortDone", 
                       title="Velocity (Story Points)", markers=True)

        # Force y-axis to start at 0 and avoid negative values
        fig1.update_layout(
            yaxis=dict(range=[0, max(1, df_filtered["SumEffortDone"].max())], title="US Points delivered"),
            xaxis=dict(title="Sprints")
        )

        # Display the first chart
        st.plotly_chart(fig1, use_container_width=True)

        # Create the first line chart (Done User Stories)
        fig2 = px.line(df_filtered, x="IterationName", y="DoneUserStories", 
                       title="Number of stories Done", markers=True)
        
        # Force y-axis to start at 0 and avoid negative values
        fig2.update_layout(
            yaxis=dict(range=[0, max(1, df_filtered["DoneUserStories"].max())], title="Number of user stories"),
            xaxis=dict(title="Sprints")
        )

        # Display the second chart
        st.plotly_chart(fig2, use_container_width=True)

    else:
        st.warning(f"Required fields {required_columns} are missing.")
