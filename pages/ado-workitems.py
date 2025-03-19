import streamlit as st
import pandas as pd
from pymongo import MongoClient
from modules.refresh_ado_workitems import refresh_work_items

# Load secrets
mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]
project_name = "P3-Tech-Master"

st.title("Your ADO Work Items")

# Button to refresh work items
if st.button("Refresh work items list"):
    with st.spinner("Fetching work items..."):
        refresh_work_items()
    st.success("Work items refreshed successfully!")

# Connect to MongoDB and fetch data
client = MongoClient(mongo_uri)
db = client[db_name]
collection_name = f"{project_name}-ado-workitems"
collection = db[collection_name]

# Load work items into a DataFrame
work_items = list(collection.find({}, {"_id": 0}))  # Exclude MongoDB's default _id field

df = pd.DataFrame(work_items)

if not df.empty:
    st.dataframe(df)
else:
    st.write("No work items found.")
