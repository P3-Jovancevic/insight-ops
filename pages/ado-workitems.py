import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient
from datetime import datetime, timedelta
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

    # --- Cumulative Flow Diagram (CFD) ---
    st.subheader("Cumulative Flow Diagram")

    # Date filter (default: last 3 months)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=90)
    date_range = st.date_input("Select Date Range", (start_date, end_date))

    # Ensure date input is valid
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        st.warning("Invalid date range selected.")
        st.stop()

    # Convert date fields
    df["System_ChangedDate"] = pd.to_datetime(df["System_ChangedDate"], errors="coerce")

    # Filter by date range
    df_filtered = df[(df["System_ChangedDate"] >= pd.Timestamp(start_date)) &
                     (df["System_ChangedDate"] <= pd.Timestamp(end_date))]

    # Group by date and state
    if not df_filtered.empty:
        cfd_data = df_filtered.groupby([df_filtered["System_ChangedDate"].dt.date, "System_State"]) \
                              .size().reset_index(name="Count")

        # Create Cumulative Flow Diagram
        fig = px.area(cfd_data, x="System_ChangedDate", y="Count", color="System_State",
                      title="Cumulative Flow Diagram",
                      labels={"System_ChangedDate": "Date", "Count": "Work Items", "System_State": "State"},
                      line_group="System_State")

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No work items found in the selected date range.")
