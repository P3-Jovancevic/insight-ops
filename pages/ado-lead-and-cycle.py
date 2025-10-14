import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# ---------------------------------------------
# PAGE TITLE
# ---------------------------------------------
st.title("Lead Time Summary by Iteration")

# ---------------------------------------------
# CONNECT TO MONGO
# ---------------------------------------------
try:
    mongo_uri = st.secrets["mongo"]["uri"]
    db_name = st.secrets["mongo"]["db_name"]

    client = MongoClient(mongo_uri)
    db = client[db_name]

    iterations_col = db["ado-iterations"]
    workitems_col = db["ado-workitems"]

except Exception as e:
    st.error(f"Failed to connect to MongoDB: {e}")
    st.stop()

# ---------------------------------------------
# LOAD DATA FROM MONGO
# ---------------------------------------------
try:
    iterations = list(iterations_col.find({}, {"_id": 0, "path": 1, "startDate": 1, "finishDate": 1}))
    workitems = list(workitems_col.find({}, {
        "_id": 0,
        "System_CreatedDate": 1,
        "Microsoft_VSTS_Common_ClosedDate": 1,
        "System_IterationPath": 1
    }))
except Exception as e:
    st.error(f"Error loading data from MongoDB: {e}")
    st.stop()

if not iterations or not workitems:
    st.warning("No data found in MongoDB collections.")
    st.stop()

# ---------------------------------------------
# CONVERT TO DATAFRAMES AND NORMALIZE DATES
# ---------------------------------------------
iterations_df = pd.DataFrame(iterations)
workitems_df = pd.DataFrame(workitems)

# Convert string dates to UTC datetime
iterations_df["startDate"] = pd.to_datetime(iterations_df["startDate"], utc=True, errors="coerce")
iterations_df["finishDate"] = pd.to_datetime(iterations_df["finishDate"], utc=True, errors="coerce")
workitems_df["System_CreatedDate"] = pd.to_datetime(workitems_df["System_CreatedDate"], utc=True, errors="coerce")
workitems_df["Microsoft_VSTS_Common_ClosedDate"] = pd.to_datetime(workitems_df["Microsoft_VSTS_Common_ClosedDate"], utc=True, errors="coerce")

# Drop rows with missing CreatedDate
workitems_df = workitems_df.dropna(subset=["System_CreatedDate"])

# ---------------------------------------------
# CALCULATE LEAD TIME (CLOSED OR ONGOING)
# ---------------------------------------------
now = datetime.now(timezone.utc)

def calc_lead_time(row):
    closed = row["Microsoft_VSTS_Common_ClosedDate"]
    created = row["System_CreatedDate"]
    if pd.isna(created):
        return None
    if pd.isna(closed):
        return (now - created).days
    else:
        return (closed - created).days

workitems_df["LeadTimeDays"] = workitems_df.apply(calc_lead_time, axis=1)

# ---------------------------------------------
# FIND LATEST ITERATION
# ---------------------------------------------
latest_iteration = iterations_df.sort_values(by="finishDate", ascending=False).iloc[0]
latest_finish = latest_iteration["finishDate"]
cutoff_date = latest_finish - timedelta(days=15)

# ---------------------------------------------
# CALCULATE METRICS
# ---------------------------------------------
overall_lead_time = workitems_df["LeadTimeDays"].mean()

recent_items = workitems_df[workitems_df["System_CreatedDate"] > cutoff_date]
recent_lead_time = recent_items["LeadTimeDays"].mean() if not recent_items.empty else None

# ---------------------------------------------
# DISPLAY SCORECARDS
# ---------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Overall Lead Time (All Work Items)",
        value=f"{overall_lead_time:.2f} days" if overall_lead_time else "N/A"
    )

with col2:
    st.metric(
        label="Lead Time (Last 15 Days of Development)",
        value=f"{recent_lead_time:.2f} days" if recent_lead_time else "N/A"
    )

# ---------------------------------------------
# OPTIONAL: DETAILS BELOW
# ---------------------------------------------
with st.expander("See data details"):
    st.write("### Latest Iteration")
    st.dataframe(latest_iteration.to_frame().T)

    st.write("### Work Items Sample")
    st.dataframe(workitems_df.head())

    # ---------------------------------------------
    # NEW SECTION: LEAD TIME SUMMARY STATS
    # ---------------------------------------------
    st.write("### Work Item Lead Time Summary")

    # Filter out NaN or negative lead times (if any)
    valid_lead_times = workitems_df["LeadTimeDays"].dropna()
    valid_lead_times = valid_lead_times[valid_lead_times >= 0]

    if not valid_lead_times.empty:
        stats = {
            "Min Lead Time (days)": valid_lead_times.min(),
            "Max Lead Time (days)": valid_lead_times.max(),
            "Average Lead Time (days)": valid_lead_times.mean(),
            "Median Lead Time (days)": valid_lead_times.median()
        }

        summary_df = pd.DataFrame(list(stats.items()), columns=["Metric", "Value"])
        st.dataframe(summary_df, use_container_width=True)
    else:
        st.info("No valid lead time data available for summary.")
