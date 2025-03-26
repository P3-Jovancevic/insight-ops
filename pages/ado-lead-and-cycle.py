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
    required_columns = {"Date", "Iteration", "CycleTime", "LeadTime"}
    
    # Query MongoDB to get the lead and cycle time data
    data = list(collection.find({"LeadTime": {"$ne": None}, "CycleTime": {"$ne": None}}))

    # Convert the data to a pandas DataFrame
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date'])  # Ensure Date is in datetime format

    # Plot Lead Time and Cycle Time over Time
    fig = px.line(df, x='Date', y=['LeadTime', 'CycleTime'], 
                title="Lead Time and Cycle Time Over Time", 
                labels={'LeadTime': 'Lead Time (Days)', 'CycleTime': 'Cycle Time (Days)'})

    # Show the plot in Streamlit
    st.plotly_chart(fig)