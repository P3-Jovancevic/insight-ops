import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import plotly.express as px
import logging

# ---------------------------------------------
# PAGE TITLE
# ---------------------------------------------
st.title("Lead Time, Cycle Time & Burn-Up Summary")

# ---------------------------------------------
# SESSION AUTHENTICATION
# ---------------------------------------------
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    st.error("You are not logged in. Go to login page.")
    st.stop()

if "user_email" not in st.session_state:
    st.error("Session invalid. Please log in again.")
    st.stop()

user_email = st.session_state["user_email"]

# ---------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------
mongo_uri = st.secrets["mongo"]["uri"]
client = MongoClient(mongo_uri)
db = client["insight-ops"]

# ---------------------------------------------
# PAGE LOGIC
# ---------------------------------------------
st.markdown("### Data Summary Overview")

# Collections
workitems_collection = db["ado-workitems"]
iterations_collection = db["ado-iterations"]

# Load data
work_items = list(workitems_collection.find({}))
iterations = list(iterations_collection.find({}))

if not work_items or not iterations:
    st.warning("No data found in MongoDB. Please refresh from Azure DevOps.")
    st.stop()

df_workitems = pd.DataFrame(work_items)
df_iterations = pd.DataFrame(iterations)

# ---------------------------------------------
# DATA CLEANUP AND PREPARATION
# ---------------------------------------------
df_workitems["CreatedDate"] = pd.to_datetime(df_workitems["System_CreatedDate"], errors="coerce")
df_workitems["ClosedDate"] = pd.to_datetime(df_workitems["Microsoft_VSTS_Common_ClosedDate"], errors="coerce")

df_workitems = df_workitems[df_workitems["System_WorkItemType"] == "User Story"]

# Calculate lead time (Created → Closed)
df_workitems["LeadTimeDays"] = (df_workitems["ClosedDate"] - df_workitems["CreatedDate"]).dt.days

# Cycle time (Activated → Closed)
if "Microsoft_VSTS_Common_ActivatedDate" in df_workitems.columns:
    df_workitems["ActivatedDate"] = pd.to_datetime(df_workitems["Microsoft_VSTS_Common_ActivatedDate"], errors="coerce")
    df_workitems["CycleTimeDays"] = (df_workitems["ClosedDate"] - df_workitems["ActivatedDate"]).dt.days
else:
    df_workitems["CycleTimeDays"] = None

# ---------------------------------------------
# METRICS SUMMARY
# ---------------------------------------------
lead_time_avg = df_workitems["LeadTimeDays"].mean()
cycle_time_avg = df_workitems["CycleTimeDays"].mean()

st.metric("Average Lead Time (days)", f"{lead_time_avg:.1f}" if pd.notna(lead_time_avg) else "N/A")
st.metric("Average Cycle Time (days)", f"{cycle_time_avg:.1f}" if pd.notna(cycle_time_avg) else "N/A")

# ---------------------------------------------
# BURN-UP CHARTS
# ---------------------------------------------
st.markdown("### Burn-Up Chart (Count of User Stories)")

df_burnup = df_workitems.copy()
df_burnup = df_burnup[df_burnup["ClosedDate"].notna()]
df_burnup = df_burnup.groupby(df_burnup["ClosedDate"].dt.date).size().cumsum().reset_index()
df_burnup.columns = ["Date", "CumulativeStories"]

fig1 = px.line(df_burnup, x="Date", y="CumulativeStories", title="Burn-Up Chart - User Stories")
st.plotly_chart(fig1, use_container_width=True)

# ---------------------------------------------
# EFFORT-BASED BURN-UP
# ---------------------------------------------
st.markdown("### Burn-Up Chart (Effort-Based)")

if "Microsoft_VSTS_Scheduling_Effort" in df_workitems.columns:
    df_effort = df_workitems[df_workitems["ClosedDate"].notna()].copy()
    df_effort["Effort"] = pd.to_numeric(df_effort["Microsoft_VSTS_Scheduling_Effort"], errors="coerce").fillna(0)
    df_effort = df_effort.groupby(df_effort["ClosedDate"].dt.date)["Effort"].sum().cumsum().reset_index()
    df_effort.columns = ["Date", "CumulativeEffort"]

    fig2 = px.line(df_effort, x="Date", y="CumulativeEffort", title="Burn-Up Chart - Effort (Story Points)")
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No 'Effort' data found in work items.")

# ---------------------------------------------
# REFRESH DATA BUTTON
# ---------------------------------------------
st.markdown("---")
st.markdown("### Refresh Data")

if st.button("↻ Refresh"):
    try:
        from modules.refresh_iterations import refresh_iterations
        from modules.refresh_workitems import refresh_workitems

        refresh_iterations()
        refresh_workitems()
        st.success("Work items refreshed successfully!")
        st.rerun()
    except Exception as e:
        logging.exception("Failed to refresh data")
        st.error(f"Error refreshing data: {e}")
