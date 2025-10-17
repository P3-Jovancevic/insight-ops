import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timezone
import plotly.express as px

# ---------------------------------------------
# PAGE TITLE
# ---------------------------------------------
st.title("Lead Time, Cycle Time & Burn-Up Summary")

# ---------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------
mongo_uri = st.secrets["mongo"]["mongo_uri"]
client = MongoClient(mongo_uri)
db = client["insight-ops"]

# ---------------------------------------------
# LOAD DATA
# ---------------------------------------------
workitems_data = list(db["ado-workitems"].find())
iterations_data = list(db["ado-iterations"].find())

if not workitems_data or not iterations_data:
    st.warning("No data found in MongoDB. Please refresh data first.")
    st.stop()

workitems_df = pd.DataFrame(workitems_data)
iterations_df = pd.DataFrame(iterations_data)

# ---------------------------------------------
# CLEAN AND PREPARE DATA
# ---------------------------------------------
# Convert datetime columns
date_columns = [
    "System_CreatedDate",
    "Microsoft_VSTS_Common_ClosedDate",
    "IterationStartDate",
    "IterationEndDate",
]
for col in date_columns:
    if col in workitems_df.columns:
        workitems_df[col] = pd.to_datetime(workitems_df[col], errors="coerce")

now = datetime.now(timezone.utc)

# ---------------------------------------------
# VECTORIZED CALCULATIONS
# ---------------------------------------------
closed_filled_for_lead = workitems_df["Microsoft_VSTS_Common_ClosedDate"].fillna(pd.Timestamp(now))
lead_timedelta = closed_filled_for_lead - workitems_df["System_CreatedDate"]
workitems_df["LeadTimeDays"] = lead_timedelta.dt.days

closed_filled_for_cycle = workitems_df["Microsoft_VSTS_Common_ClosedDate"].fillna(pd.Timestamp(now))
cycle_timedelta = closed_filled_for_cycle - workitems_df["IterationStartDate"]
workitems_df["CycleTimeDays"] = cycle_timedelta.dt.days

# ---------------------------------------------
# FILTER RELEVANT WORK ITEMS
# ---------------------------------------------
workitems_df = workitems_df[workitems_df["System_WorkItemType"] == "User Story"]
workitems_df = workitems_df.dropna(subset=["IterationPath", "System_CreatedDate"])

# ---------------------------------------------
# MERGE WITH ITERATIONS
# ---------------------------------------------
if "Path" in iterations_df.columns:
    merged_df = pd.merge(
        workitems_df,
        iterations_df[["Path", "StartDate", "EndDate"]],
        left_on="IterationPath",
        right_on="Path",
        how="left",
    )
else:
    st.warning("Iteration data missing 'Path' column.")
    st.stop()

# ---------------------------------------------
# BURN-UP CHART PREPARATION
# ---------------------------------------------
merged_df["EndDate"] = pd.to_datetime(merged_df["EndDate"], errors="coerce")
merged_df["ClosedDate"] = pd.to_datetime(merged_df["Microsoft_VSTS_Common_ClosedDate"], errors="coerce")

# Group by Iteration and count effort and closed items
effort_col = "Microsoft_VSTS_Scheduling_Effort"
if effort_col in merged_df.columns:
    merged_df[effort_col] = pd.to_numeric(merged_df[effort_col], errors="coerce").fillna(0)
else:
    merged_df[effort_col] = 0

iteration_summary = (
    merged_df.groupby("IterationPath")
    .agg(
        TotalEffort=(effort_col, "sum"),
        ClosedEffort=("ClosedDate", lambda x: merged_df.loc[x.notna(), effort_col].sum()),
        AvgLeadTime=("LeadTimeDays", "mean"),
        AvgCycleTime=("CycleTimeDays", "mean"),
    )
    .reset_index()
)

iteration_summary = iteration_summary.sort_values("IterationPath", ascending=True)

# ---------------------------------------------
# DISPLAY TABLE
# ---------------------------------------------
st.subheader("Iteration Summary (Effort, Lead, and Cycle Time)")
st.dataframe(
    iteration_summary[
        ["IterationPath", "TotalEffort", "ClosedEffort", "AvgLeadTime", "AvgCycleTime"]
    ]
)

# ---------------------------------------------
# BURN-UP CHART
# ---------------------------------------------
st.subheader("Burn-Up Chart (Effort)")
fig = px.line(
    iteration_summary,
    x="IterationPath",
    y=["ClosedEffort", "TotalEffort"],
    markers=True,
    title="Burn-Up Chart by Effort",
    labels={"value": "Effort", "IterationPath": "Iteration"},
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------
# SECOND CHART (COUNT OF USER STORIES)
# ---------------------------------------------
count_summary = (
    merged_df.groupby("IterationPath")
    .agg(
        TotalStories=("System_Id", "count"),
        ClosedStories=("ClosedDate", lambda x: x.notna().sum()),
    )
    .reset_index()
)

count_summary = count_summary.sort_values("IterationPath", ascending=True)

st.subheader("Burn-Up Chart (User Story Count)")
fig2 = px.line(
    count_summary,
    x="IterationPath",
    y=["ClosedStories", "TotalStories"],
    markers=True,
    title="Burn-Up Chart by Story Count",
    labels={"value": "User Stories", "IterationPath": "Iteration"},
)
st.plotly_chart(fig2, use_container_width=True)

# ---------------------------------------------
# CLEANUP
# ---------------------------------------------
client.close()
