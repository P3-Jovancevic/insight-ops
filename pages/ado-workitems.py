import streamlit as st
import pandas as pd
import plotly.express as px
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

    # Ensure System_ChangedDate is in datetime format
    if "System_ChangedDate" in df.columns:
        df["System_ChangedDate"] = pd.to_datetime(df["System_ChangedDate"], errors="coerce")

        # Date filter - Default to last 3 months
        max_date = df["System_ChangedDate"].max()
        min_date = max_date - pd.DateOffset(months=3) if pd.notna(max_date) else pd.Timestamp.today() - pd.DateOffset(months=3)
        start_date, end_date = st.date_input("Select Date Range:", [min_date, max_date])
        
        # Convert to Timestamp for filtering
        start_date = pd.Timestamp(start_date)
        end_date = pd.Timestamp(end_date)
        
        # Filter data based on date selection
        df_filtered = df[(df["System_ChangedDate"] >= start_date) & (df["System_ChangedDate"] <= end_date)]

        # Create Cumulative Flow Diagram (CFD)
        if not df_filtered.empty:
            cfd_fig = px.area(
                df_filtered,
                x="System_ChangedDate",
                color="System_State",
                title="Cumulative Flow Diagram",
                labels={"System_ChangedDate": "Date", "System_State": "Work Item State"},
                category_orders={"System_State": sorted(df_filtered["System_State"].unique())}
            )
            st.plotly_chart(cfd_fig)
        else:
            st.warning("No work items found in the selected date range.")
