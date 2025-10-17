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
        "System_WorkItemType": 1,
        "Microsoft_VSTS_Scheduling_Effort": 1,
        "Microsoft_VSTS_Common_ActivatedDate": 1
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
    date_range = pd.date_range(start=min_date, end=max_date, freq="D")

    cfd_data = []

    for current_date in date_range:
        todo_count = ((workitems_df["System_CreatedDate"] <= current_date) &
                      ((workitems_df["Microsoft_VSTS_Common_ActivatedDate"].isna()) |
                       (workitems_df["Microsoft_VSTS_Common_ActivatedDate"] > current_date))).sum()

        in_progress_count = ((workitems_df["Microsoft_VSTS_Common_ActivatedDate"] <= current_date) &
                             ((workitems_df["Microsoft_VSTS_Common_ClosedDate"].isna()) |
                              (workitems_df["Microsoft_VSTS_Common_ClosedDate"] > current_date))).sum()

        done_count = (workitems_df["Microsoft_VSTS_Common_ClosedDate"] <= current_date).sum()

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

# Ensure the Effort field exists
effort_field = "Microsoft_VSTS_Scheduling_Effort"
if effort_field not in workitems_df.columns:
    st.info("No effort field found for CFD.")
else:
    # Use activated date for 'In Progress', closed date for 'Done'
    workitems_df["ActivatedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ActivatedDate"), utc=True, errors="coerce")
    workitems_df["ClosedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ClosedDate"), utc=True, errors="coerce")

    # Create daily date range from earliest creation to latest close
    min_date = workitems_df["System_CreatedDate"].min().normalize()
    max_date = workitems_df[["System_CreatedDate", "ActivatedDate", "ClosedDate"]].max().max().normalize()
    date_range = pd.date_range(start=min_date, end=max_date, freq="D")

    cfd_data = []
    for current_date in date_range:
        # Done: closed <= current_date
        done_effort = workitems_df.loc[
            workitems_df["ClosedDate"].notna() & (workitems_df["ClosedDate"] <= current_date),
            effort_field
        ].sum(skipna=True)

        # In Progress: activated <= current_date and (closed > current_date or not closed)
        in_progress_effort = workitems_df.loc[
            (workitems_df["ActivatedDate"].notna()) &
            (workitems_df["ActivatedDate"] <= current_date) &
            ((workitems_df["ClosedDate"].isna()) | (workitems_df["ClosedDate"] > current_date)),
            effort_field
        ].sum(skipna=True)

        # To Do: created <= current_date and (not activated or activated > current_date)
        todo_effort = workitems_df.loc[
            (workitems_df["System_CreatedDate"] <= current_date) &
            ((workitems_df["ActivatedDate"].isna()) | (workitems_df["ActivatedDate"] > current_date)),
            effort_field
        ].sum(skipna=True)

        cfd_data.append({
            "Date": current_date,
            "To Do": todo_effort,
            "In Progress": in_progress_effort,
            "Done": done_effort
        })

    cfd_df = pd.DataFrame(cfd_data)

    # Plot area chart (stacked), reverse order: Done on bottom, In Progress middle, To Do top
    fig_cfd = px.area(
        cfd_df,
        x="Date",
        y=["To Do", "In Progress", "Done"][::-1],  # Reverse order
        labels={"value": "Effort / Story Points", "Date": "Date", "variable": "State"},
        title="Cumulative Flow Diagram (Effort-Based)"
    )

    # Assign colors: Done green, In Progress blue, To Do gray
    fig_cfd.update_traces(selector=dict(name="Done"), fillcolor="green")
    fig_cfd.update_traces(selector=dict(name="In Progress"), fillcolor="blue")
    fig_cfd.update_traces(selector=dict(name="To Do"), fillcolor="gray")

    st.plotly_chart(fig_cfd, use_container_width=True)

# ---------------------------------------------
# ESTIMATE ACCURACY SCORECARDS
# ---------------------------------------------
# Only consider work items with effort and activated/closed dates
effort_items = workitems_df.dropna(subset=["Microsoft_VSTS_Scheduling_Effort", "Microsoft_VSTS_Common_ActivatedDate", "Microsoft_VSTS_Common_ClosedDate"]).copy()

# Calculate actual cycle time in days
effort_items["ActualCycleDays"] = (effort_items["Microsoft_VSTS_Common_ClosedDate"] - effort_items["Microsoft_VSTS_Common_ActivatedDate"]).dt.days

# Exclude items with zero or negative cycle time
effort_items = effort_items[effort_items["ActualCycleDays"] > 0]

# Calculate Estimate Accuracy = Effort / ActualCycleDays
effort_items["EstimateAccuracy"] = effort_items["Microsoft_VSTS_Scheduling_Effort"] / effort_items["ActualCycleDays"]

# Overall Estimate Accuracy
overall_estimate_accuracy = effort_items["EstimateAccuracy"].mean() if not effort_items.empty else None

# Last Iteration Estimate Accuracy
last_iter_path = latest_iteration["path"]
last_iter_items = effort_items[effort_items["System_IterationPath"] == last_iter_path]
last_iter_estimate_accuracy = last_iter_items["EstimateAccuracy"].mean() if not last_iter_items.empty else None

# ---------------------------------------------
# DISPLAY ESTIMATE ACCURACY SCORECARDS
# ---------------------------------------------
st.subheader("Estimate Accuracy (Planned Effort / Actual Cycle Time)")

col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Overall Estimate Accuracy",
        value=f"{overall_estimate_accuracy:.2f}" if overall_estimate_accuracy else "N/A"
    )

with col2:
    st.metric(
        label=f"Estimate Accuracy (Last Iteration: {last_iter_path.split('\\\\')[-1]})",
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
