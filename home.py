import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import plotly.express as px
from modules.refresh_ado_workitems import refresh_work_items
from modules.refresh_iterations import refresh_iterations  # updated import

# ---------------------------------------------
# PAGE TITLE
# ---------------------------------------------
st.title("Lead Time, Cycle Time & Burn-Up Summary")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None

if not st.session_state["logged_in"]:
    st.error("You are not logged in. Go to login page.")
    st.stop()

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
        "System_WorkItemType": 1,
        "Microsoft_VSTS_Scheduling_Effort": 1,
        "Microsoft_VSTS_Common_ActivatedDate": 1
    }))
except Exception as e:
    st.error(f"Error loading data from MongoDB: {e}")
    st.stop()

if not iterations or not workitems:

    required_fields = ["organization_url", "project_name", "team_name", "pat"]
    missing_fields = [f for f in required_fields if not user.get(f)]
    all_fields_present = len(missing_fields) == 0

    if not all_fields_present:
        st.info("Please set up your Azure DevOps connection details (organization URL, project name, team name, and PAT) before refreshing.")
        if user and missing_fields:
            st.write(f"⚠️ Missing fields: {', '.join(missing_fields)}")

    if st.button("↻ Refresh", disabled=not all_fields_present):
        refresh_iterations()
        refresh_work_items()
        st.success("Refreshed successfully!")
        st.rerun()

    st.warning("No data found in MongoDB collections.")
    st.stop()
    
# ---------------------------------------------
# CONVERT TO DATAFRAMES AND NORMALIZE DATES
# ---------------------------------------------
iterations_df = pd.DataFrame(iterations)
workitems_df = pd.DataFrame(workitems)

# ✅ FILTER ONLY USER STORIES / PBIs
valid_types = ["User Story", "PBI", "Product Backlog Item"]
workitems_df = workitems_df[workitems_df["System_WorkItemType"].isin(valid_types)]

if workitems_df.empty:
    st.warning("No User Stories or PBIs found in the work items collection.")
    st.stop()

# Convert string dates to UTC datetime
iterations_df["startDate"] = pd.to_datetime(iterations_df["startDate"], utc=True, errors="coerce")
iterations_df["finishDate"] = pd.to_datetime(iterations_df["finishDate"], utc=True, errors="coerce")
workitems_df["System_CreatedDate"] = pd.to_datetime(workitems_df["System_CreatedDate"], utc=True, errors="coerce")
workitems_df["Microsoft_VSTS_Common_ClosedDate"] = pd.to_datetime(workitems_df["Microsoft_VSTS_Common_ClosedDate"], utc=True, errors="coerce")

# Drop work items with missing created date
workitems_df = workitems_df.dropna(subset=["System_CreatedDate"])

# ---------------------------------------------
# CREATE ITERATION START DATE MAPPING
# ---------------------------------------------
iteration_start_map = iterations_df.set_index("path")["startDate"].to_dict()

# Add Cycle Start Date to each work item
def get_iteration_start(row):
    iteration_path = row["System_IterationPath"]
    return iteration_start_map.get(iteration_path, pd.NaT)

workitems_df["IterationStartDate"] = workitems_df.apply(get_iteration_start, axis=1)

# Exclude work items without valid iteration start
workitems_df = workitems_df.dropna(subset=["IterationStartDate"])

# ---------------------------------------------
# CALCULATE LEAD TIME AND CYCLE TIME
# ---------------------------------------------
now = datetime.now(timezone.utc)

def calc_lead_time(row):
    closed = row["Microsoft_VSTS_Common_ClosedDate"]
    created = row["System_CreatedDate"]
    if pd.isna(created):
        return None
    return (closed - created).days if not pd.isna(closed) else (now - created).days

def calc_cycle_time(row):
    closed = row["Microsoft_VSTS_Common_ClosedDate"]
    start = row["IterationStartDate"]
    if pd.isna(start):
        return None
    return (closed - start).days if not pd.isna(closed) else (now - start).days

workitems_df["LeadTimeDays"] = workitems_df.apply(calc_lead_time, axis=1)
workitems_df["CycleTimeDays"] = workitems_df.apply(calc_cycle_time, axis=1)

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
recent_lead_time = recent_lead_items["LeadTimeDays"].mean() if not recent_lead_items.empty else None

# Cycle Time
overall_cycle_time = workitems_df["CycleTimeDays"].mean()
recent_cycle_items = workitems_df[workitems_df["System_CreatedDate"] > cutoff_date]
recent_cycle_time = recent_cycle_items["CycleTimeDays"].mean() if not recent_cycle_items.empty else None

# ---------------------------------------------
# REFRESH BUTTON (disabled if missing user info)
# ---------------------------------------------
user_email = st.session_state.get("user_email")
user = users_col.find_one({"email": user_email}, {"_id": 0}) if user_email else None

if not user:
    st.warning("User not found in database.")
    all_fields_present = False
else:
    required_fields = ["organization_url", "project_name", "team_name", "pat"]
    missing_fields = [f for f in required_fields if not user.get(f)]
    all_fields_present = len(missing_fields) == 0

if not all_fields_present:
    st.info("Please set up your Azure DevOps connection details (organization URL, project name, team name, and PAT) before refreshing.")
    if user and missing_fields:
        st.write(f"⚠️ Missing fields: {', '.join(missing_fields)}")

if st.button("↻ Refresh", disabled=not all_fields_present):
    refresh_iterations()
    refresh_work_items()
    st.success("Refreshed successfully!")
    st.rerun()

# ---------------------------------------------
# DISPLAY SCORECARDS
# ---------------------------------------------
st.subheader("Scorecards")
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Overall Lead Time (All User Stories/PBIs)",
        value=f"{overall_lead_time:.2f} days" if overall_lead_time else "N/A"
    )

with col2:
    st.metric(
        label="Lead Time (Last 30 Days of Development)",
        value=f"{recent_lead_time:.2f} days" if recent_lead_time else "N/A"
    )

col3, col4 = st.columns(2)
with col3:
    st.metric(
        label="Overall Cycle Time (All User Stories/PBIs)",
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
    title="Burn-Up Chart (Cumulative User Stories / PBIs)",
    labels={"value": "User Stories / PBIs", "FinishDate": "Iteration Finish Date"},
)
fig_burnup.update_traces(mode="lines+markers")
fig_burnup.update_layout(legend_title_text="Metric", legend=dict(x=0.05, y=0.95))

st.plotly_chart(fig_burnup, use_container_width=True)

# ---------------------------------------------
# BURN-UP CHART (EFFORT-BASED)
# ---------------------------------------------
if "Microsoft_VSTS_Scheduling_Effort" in workitems_df.columns:
    st.subheader("Burn-Up Chart (Effort / Story Points)")

    burnup_effort_data = []
    for _, iteration in iterations_df.iterrows():
        path = iteration["path"]
        finish_date = iteration["finishDate"]
        iteration_items = workitems_df[workitems_df["System_IterationPath"] == path]

        total_effort = iteration_items["Microsoft_VSTS_Scheduling_Effort"].sum(skipna=True)
        completed_effort = iteration_items.loc[
            iteration_items["Microsoft_VSTS_Common_ClosedDate"].notna(), "Microsoft_VSTS_Scheduling_Effort"
        ].sum(skipna=True)

        burnup_effort_data.append({
            "IterationPath": path,
            "FinishDate": finish_date,
            "TotalEffort": total_effort,
            "CompletedEffort": completed_effort
        })

    burnup_effort_df = pd.DataFrame(burnup_effort_data).sort_values("FinishDate")

    # Cumulative effort over iterations
    burnup_effort_df["CumulativeTotal"] = burnup_effort_df["TotalEffort"].cumsum()
    burnup_effort_df["CumulativeCompleted"] = burnup_effort_df["CompletedEffort"].cumsum()

    # Plotly chart
    fig_effort = px.line(
        burnup_effort_df,
        x="FinishDate",
        y=["CumulativeTotal", "CumulativeCompleted"],
        markers=True,
        title="Burn-Up Chart (Cumulative Effort / Story Points)",
        labels={"value": "Effort / Story Points", "FinishDate": "Iteration Finish Date"},
    )
    fig_effort.update_traces(mode="lines+markers")
    fig_effort.update_layout(legend_title_text="Metric", legend=dict(x=0.05, y=0.95))

    st.plotly_chart(fig_effort, use_container_width=True)
else:
    st.info("No effort field found in work items for effort-based burn-up chart.")

# ---------------------------------------------
# CUMULATIVE FLOW DIAGRAM (CFD)
# ---------------------------------------------
st.subheader("Cumulative Flow Diagram (CFD)")

if "Microsoft_VSTS_Common_ActivatedDate" in workitems_df.columns:
    # Convert to datetime
    workitems_df["Microsoft_VSTS_Common_ActivatedDate"] = pd.to_datetime(
        workitems_df["Microsoft_VSTS_Common_ActivatedDate"], utc=True, errors="coerce"
    )

    # Determine date range
    min_date = workitems_df["System_CreatedDate"].min()
    max_date_candidates = [workitems_df["Microsoft_VSTS_Common_ClosedDate"].max(),
                           workitems_df["Microsoft_VSTS_Common_ActivatedDate"].max()]
    max_date = max([d for d in max_date_candidates if pd.notna(d)])

    # Extend by 1 day to show final merge
    date_range = pd.date_range(start=min_date, end=max_date + pd.Timedelta(days=1), freq="D")

    cfd_data = []

    for current_date in date_range:
        done_count = ((workitems_df["Microsoft_VSTS_Common_ActivatedDate"].notna()) &
                      (workitems_df["Microsoft_VSTS_Common_ClosedDate"].notna()) &
                      (workitems_df["Microsoft_VSTS_Common_ClosedDate"] <= current_date)).sum()

        in_progress_count = ((workitems_df["Microsoft_VSTS_Common_ActivatedDate"].notna()) &
                             ((workitems_df["Microsoft_VSTS_Common_ClosedDate"].isna()) |
                              (workitems_df["Microsoft_VSTS_Common_ClosedDate"] > current_date))).sum()

        todo_count = len(workitems_df) - done_count - in_progress_count

        cfd_data.append({
            "Date": current_date,
            "Done": done_count,
            "In Progress": in_progress_count,
            "To Do": todo_count
        })

    cfd_df = pd.DataFrame(cfd_data)

    # Plot CFD as stacked area chart with reversed stack order
    fig_cfd = px.area(
        cfd_df,
        x="Date",
        y=["Done", "In Progress", "To Do"],  # Done at bottom, To Do on top
        title="Cumulative Flow Diagram (User Stories / PBIs)",
        labels={"value": "Number of Stories", "Date": "Date", "variable": "State"},
        color_discrete_map={"Done": "green", "In Progress": "blue", "To Do": "gray"}
    )
    st.plotly_chart(fig_cfd, use_container_width=True)

else:
    st.info("Activated date field not found. Cannot generate Cumulative Flow Diagram.")


# ---------------------------------------------
# CUMULATIVE FLOW DIAGRAM (EFFORT-BASED)
# ---------------------------------------------
st.subheader("Cumulative Flow Diagram (Effort-Based)")

effort_field = "Microsoft_VSTS_Scheduling_Effort"
if effort_field not in workitems_df.columns:
    st.info("No effort field found for CFD.")
else:
    workitems_df["ActivatedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ActivatedDate"), utc=True, errors="coerce")
    workitems_df["ClosedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ClosedDate"), utc=True, errors="coerce")

    min_date = workitems_df["System_CreatedDate"].min().normalize()
    max_date = workitems_df[["System_CreatedDate", "ActivatedDate", "ClosedDate"]].max().max().normalize()

    # Extend by 1 day
    date_range = pd.date_range(start=min_date, end=max_date + pd.Timedelta(days=1), freq="D")

    cfd_data = []
    for current_date in date_range:
        done_effort = workitems_df.loc[
            (workitems_df["ActivatedDate"].notna()) &
            (workitems_df["ClosedDate"].notna()) &
            (workitems_df["ClosedDate"] <= current_date),
            effort_field
        ].sum(skipna=True)

        in_progress_effort = workitems_df.loc[
            (workitems_df["ActivatedDate"].notna()) &
            ((workitems_df["ClosedDate"].isna()) | (workitems_df["ClosedDate"] > current_date)),
            effort_field
        ].sum(skipna=True)

        todo_effort = workitems_df[effort_field].sum(skipna=True) - done_effort - in_progress_effort

        cfd_data.append({
            "Date": current_date,
            "Done": done_effort,
            "In Progress": in_progress_effort,
            "To Do": todo_effort
        })

    cfd_df = pd.DataFrame(cfd_data)

    # Plot area chart (stacked), Done on bottom
    fig_cfd_effort = px.area(
        cfd_df,
        x="Date",
        y=["Done", "In Progress", "To Do"],
        labels={"value": "Effort / Story Points", "Date": "Date", "variable": "State"},
        title="Cumulative Flow Diagram (Effort-Based)",
        color_discrete_map={"Done": "green", "In Progress": "blue", "To Do": "gray"}
    )
    st.plotly_chart(fig_cfd_effort, use_container_width=True)

# ---------------------------------------------
# ESTIMATE ACCURACY SCORECARDS
# ---------------------------------------------
# Compute cycle time per story (days between ActivatedDate and ClosedDate)
workitems_df["ActivatedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ActivatedDate"), utc=True, errors="coerce")
workitems_df["ClosedDate"] = workitems_df["Microsoft_VSTS_Common_ClosedDate"]

def calc_cycle_time_effort(row):
    start = row["ActivatedDate"]
    end = row["ClosedDate"]
    effort = row.get("Microsoft_VSTS_Scheduling_Effort", 0)
    if pd.isna(start) or pd.isna(end) or not effort or effort == 0:
        return None
    return (end - start).days / effort if effort else None

workitems_df["EstimateAccuracy"] = workitems_df.apply(calc_cycle_time_effort, axis=1)

# Overall Estimate Accuracy
valid_estimates = workitems_df["EstimateAccuracy"].dropna()
overall_estimate_accuracy = valid_estimates.mean() if not valid_estimates.empty else None

# Last Iteration Estimate Accuracy
last_iter_path = latest_iteration["path"]
last_iter_items = workitems_df[workitems_df["System_IterationPath"] == last_iter_path]
last_iter_estimates = last_iter_items["EstimateAccuracy"].dropna()
last_iter_estimate_accuracy = last_iter_estimates.mean() if not last_iter_estimates.empty else None

last_iter_name = last_iter_path.split("\\")[-1]

st.subheader("Estimate Accuracy (Cycle Time / Story Points)")
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Overall Estimate Accuracy (All User Stories)",
        value=f"{overall_estimate_accuracy:.2f}" if overall_estimate_accuracy else "N/A"
    )

with col2:
    st.metric(
        label=f"Estimate Accuracy (Last Iteration: {last_iter_name})",
        value=f"{last_iter_estimate_accuracy:.2f}" if last_iter_estimate_accuracy else "N/A"
    )

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

    # Load and display work items from MongoDB
    def load_work_items():
        """Fetch work items from MongoDB."""
        work_items = list(workitems_col.find({}, {"_id": 0}))  # Exclude MongoDB's _id field
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
