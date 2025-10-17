import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import plotly.express as px

# ---------------------------------------------
# PAGE TITLE
# ---------------------------------------------
st.title("Lead Time, Cycle Time & Burn-Up Summary")

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
        "System_IterationPath": 1,
        # keep other fields unchanged for future changes (like effort) if present
        "System_WorkItemType": 1,
        "Microsoft_VSTS_Scheduling_Effort": 1,
        "StoryPoints": 1
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

# Safe datetime conversion helper
def safe_to_datetime(series):
    return pd.to_datetime(series, utc=True, errors="coerce")

# Convert string dates to UTC datetime
iterations_df["startDate"] = safe_to_datetime(iterations_df.get("startDate"))
iterations_df["finishDate"] = safe_to_datetime(iterations_df.get("finishDate"))
workitems_df["System_CreatedDate"] = safe_to_datetime(workitems_df.get("System_CreatedDate"))
workitems_df["Microsoft_VSTS_Common_ClosedDate"] = safe_to_datetime(workitems_df.get("Microsoft_VSTS_Common_ClosedDate"))

# Drop work items with missing created date (consistent with previous behavior)
workitems_df = workitems_df.dropna(subset=["System_CreatedDate"])

# ---------------------------------------------
# CREATE ITERATION START DATE MAPPING
# ---------------------------------------------
iteration_start_map = iterations_df.set_index("path")["startDate"].to_dict()

# Add Cycle Start Date to each work item (vectorized map)
workitems_df["IterationStartDate"] = workitems_df["System_IterationPath"].map(iteration_start_map)

# Exclude work items without valid iteration start (same as before)
workitems_df = workitems_df.dropna(subset=["IterationStartDate"])

# ---------------------------------------------
# CALCULATE LEAD TIME AND CYCLE TIME (VECTORIZED)
# ---------------------------------------------
now = datetime.now(timezone.utc)

# Ensure closed date column exists; already converted above
# For Lead Time: if ClosedDate is present, use (Closed - Created), else use (now - Created)
closed_filled_for_lead = workitems_df["Microsoft_VSTS_Common_ClosedDate"].fillna(pd.Timestamp(now, tz=timezone.utc))
lead_timedelta = closed_filled_for_lead - workitems_df["System_CreatedDate"]
workitems_df["LeadTimeDays"] = lead_timedelta.dt.days

# For Cycle Time: if ClosedDate present, use (Closed - IterationStart), else use (now - IterationStart)
closed_filled_for_cycle = workitems_df["Microsoft_VSTS_Common_ClosedDate"].fillna(pd.Timestamp(now, tz=timezone.utc))
cycle_timedelta = closed_filled_for_cycle - workitems_df["IterationStartDate"]
workitems_df["CycleTimeDays"] = cycle_timedelta.dt.days

# If you prefer to treat negative durations (if any) as NaN, you can filter them out later when summarizing.
# ---------------------------------------------
# FIND LATEST ITERATION
# ---------------------------------------------
latest_iteration = iterations_df.sort_values(by="finishDate", ascending=False).iloc[0]
latest_finish = latest_iteration["finishDate"]
cutoff_date = latest_finish - timedelta(days=30)

# ---------------------------------------------
# CALCULATE METRICS
# ---------------------------------------------
# Lead Time
overall_lead_time = workitems_df["LeadTimeDays"].mean()
recent_lead_items = workitems_df[workitems_df["System_CreatedDate"] > cutoff_date]
recent_le_time = recent_le_items["LeadTimeDays"].mean() if not recent_le_items.empty else None

# Cycle Time
overall_cycle_time = workitems_df["CycleTimeDays"].mean()
recent_cycle_items = workitems_df[workitems_df["System_CreatedDate"] > cutoff_date]
recent_cycle_time = recent_cycle_items["CycleTimeDays"].mean() if not recent_cycle_items.empty else None

# ---------------------------------------------
# DISPLAY SCORECARDS
# ---------------------------------------------
st.subheader("Scorecards")
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Overall Lead Time (All Work Items)",
        value=f"{overall_le_time:.2f} days" if overall_le_time else "N/A"
    )

with col2:
    st.metric(
        label="Lead Time (Last 30 Days of Development)",
        value=f"{recent_le_time:.2f} days" if recent_le_time else "N/A"
    )

col3, col4 = st.columns(2)
with col3:
    st.metric(
        label="Overall Cycle Time (All Work Items)",
        value=f"{overall_cycle_time:.2f} days" if overall_cycle_time else "N/A"
    )

with col4:
    st.metric(
        label="Cycle Time (Last 30 Days of Development)",
        value=f"{recent_cycle_time:.2f} days" if recent_cycle_time else "N/A"
    )

# ---------------------------------------------
# BURN-UP CHART (Story Count)
# ---------------------------------------------
st.subheader("Burn-Up Chart (Story Count)")

# Aggregate work items per iteration
burnup_data = []
for _, iteration in iterations_df.iterrows():
    path = iteration["path"]
    finish_date = iteration["finishDate"]
    total_items = workitems_df[workitems_df["System_IterationPath"] == path]
    total_count = len(total_items)
    completed_count = len(total_items[total_items["Microsoft_VSTS_Common_ClosedDate"].notna()])
    
    burnup_data.append({
        "IterationPath": path,
        "FinishDate": finish_date,
        "TotalStories": total_count,
        "CompletedStories": completed_count
    })

burnup_df = pd.DataFrame(burnup_data).sort_values("FinishDate")

# Cumulative values across iterations (burn-up over time)
burnup_df["CumulativeTotal"] = burnup_df["TotalStories"].cumsum()
burnup_df["CumulativeCompleted"] = burnup_df["CompletedStories"].cumsum()

# Plotly chart
fig_burnup = px.line(
    burnup_df,
    x="FinishDate",
    y=["CumulativeTotal", "CumulativeCompleted"],
    markers=True,
    title="Burn-Up Chart (Cumulative User Stories)",
    labels={"value": "User Stories", "FinishDate": "Iteration Finish Date"},
)
fig_burnup.update_traces(mode="lines+markers")
fig_burnup.update_layout(legend_title_text="Metric", legend=dict(x=0.05, y=0.95))

st.plotly_chart(fig_burnup, use_container_width=True)

# ---------------------------------------------
# DETAILS SECTION
# ---------------------------------------------
with st.expander("See data details"):
    st.write("### Latest Iteration")
    st.dataframe(latest_iteration.to_frame().T)

    st.write("### Work Items Sample")
    st.dataframe(workitems_df.head())

    # Lead Time Summary
    st.write("### Work Item Lead Time Summary")
    valid_lead_times = workitems_df["LeadTimeDays"].dropna()
    valid_lead_times = valid_lead_times[valid_lead_times >= 0]

    if not valid_lead_times.empty:
        stats_lead = {
            "Min Lead Time (days)": valid_lead_times.min(),
            "Max Lead Time (days)": valid_lead_times.max(),
            "Average Lead Time (days)": valid_lead_times.mean(),
            "Median Lead Time (days)": valid_lead_times.median()
        }
        summary_df_lead = pd.DataFrame(list(stats_lead.items()), columns=["Metric", "Value"])
        st.dataframe(summary_df_lead, use_container_width=True)
    else:
        st.info("No valid lead time data available for summary.")

    # Cycle Time Summary
    st.write("### Work Item Cycle Time Summary")
    valid_cycle_times = workitems_df["CycleTimeDays"].dropna()
    valid_cycle_times = valid_cycle_times[valid_cycle_times >= 0]

    if not valid_cycle_times.empty:
        stats_cycle = {
            "Min Cycle Time (days)": valid_cycle_times.min(),
            "Max Cycle Time (days)": valid_cycle_times.max(),
            "Average Cycle Time (days)": valid_cycle_times.mean(),
            "Median Cycle Time (days)": valid_cycle_times.median()
        }
        summary_df_cycle = pd.DataFrame(list(stats_cycle.items()), columns=["Metric", "Value"])
        st.dataframe(summary_df_cycle, use_container_width=True)
    else:
        st.info("No valid cycle time data available for summary.")
