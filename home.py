import streamlit as st
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import plotly.express as px
from google import generativeai as genai
from modules.refresh_ado_workitems import refresh_work_items
from modules.refresh_iterations import refresh_iterations  # updated import
from modules.hide_pages import hide_internal_pages

# ---------------------------------------------
# HIDE PAGES FROM NAV
# ---------------------------------------------
hide_internal_pages()

# ---------------------------------------------
# PAGE TITLE
# ---------------------------------------------
st.title("Lead Time, Cycle Time & Burn-Up Summary")

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None

if not st.session_state["logged_in"]:
    st.error("You are not logged in.")
    if st.button("Go to Login / Register"):
        st.markdown(
            """
            <meta http-equiv="refresh" content="0; url='https://insight-ops.streamlit.app/login-register'">
            """,
            unsafe_allow_html=True
        )
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
    users_col = db["users"]

except Exception as e:
    st.error(f"Failed to connect to MongoDB: {e}")
    st.stop()

# ---------------------------------------------
# LOAD DATA FROM MONGO (FILTER BY ops_user)
# ---------------------------------------------
try:
    user_email = st.session_state.get("user_email")

    iterations = list(iterations_col.find(
        {"ops_user": user_email},
        {"_id": 0, "path": 1, "startDate": 1, "finishDate": 1}
    ))

    workitems = list(workitems_col.find(
        {"ops_user": user_email},
        {
            "_id": 0,
            "System_CreatedDate": 1,
            "Microsoft_VSTS_Common_ClosedDate": 1,
            "System_IterationPath": 1,
            "System_WorkItemType": 1,
            "Microsoft_VSTS_Scheduling_Effort": 1,
            "Microsoft_VSTS_Common_ActivatedDate": 1
        }
    ))
except Exception as e:
    st.error(f"Error loading data from MongoDB: {e}")
    st.stop()

if not iterations or not workitems:
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
overall_lead_time = workitems_df["LeadTimeDays"].mean()
recent_lead_items = workitems_df[workitems_df["System_CreatedDate"] > cutoff_date]
recent_lead_time = recent_lead_items["LeadTimeDays"].mean() if not recent_lead_items.empty else None

overall_cycle_time = workitems_df["CycleTimeDays"].mean()
recent_cycle_items = workitems_df[workitems_df["System_CreatedDate"] > cutoff_date]
recent_cycle_time = recent_cycle_items["CycleTimeDays"].mean() if not recent_cycle_items.empty else None

# ---------------------------------------------
# REFRESH BUTTON (disabled if missing user info)
# ---------------------------------------------
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

burnup_df["CumulativeTotal"] = burnup_df["TotalStories"].cumsum()
burnup_df["CumulativeCompleted"] = burnup_df["CompletedStories"].cumsum()

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

    burnup_effort_df["CumulativeTotal"] = burnup_effort_df["TotalEffort"].cumsum()
    burnup_effort_df["CumulativeCompleted"] = burnup_effort_df["CompletedEffort"].cumsum()

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
    # Parse activated and closed columns (keep tz-aware)
    workitems_df["Microsoft_VSTS_Common_ActivatedDate"] = pd.to_datetime(
        workitems_df["Microsoft_VSTS_Common_ActivatedDate"], utc=True, errors="coerce"
    )
    workitems_df["Microsoft_VSTS_Common_ClosedDate"] = pd.to_datetime(
        workitems_df["Microsoft_VSTS_Common_ClosedDate"], utc=True, errors="coerce"
    )

    # Normalize the relevant dates to calendar dates for daily buckets (preserves tz)
    created_norm = workitems_df["System_CreatedDate"].dt.normalize()
    activated_norm = workitems_df["Microsoft_VSTS_Common_ActivatedDate"].dt.normalize()
    closed_norm = workitems_df["Microsoft_VSTS_Common_ClosedDate"].dt.normalize()

    # Determine min and max dates based on work item activity (normalized)
    min_date = created_norm.min()
    # take latest of activated/closed (ignoring NaT)
    max_date_candidates = [activated_norm.max(), closed_norm.max()]
    max_date = max([d for d in max_date_candidates if pd.notna(d)])

    # Build inclusive daily range
    date_range = pd.date_range(start=min_date, end=max_date + pd.Timedelta(days=1), freq="D")

    cfd_data = []

    # Pre-store column series for speed
    total_count_all = len(workitems_df)

    for current_date in date_range:
        # current_date is midnight of the day (Timestamp)
        # Masks for states (Done overrides In Progress)
        done_mask = (closed_norm.notna()) & (closed_norm <= current_date)

        in_progress_mask = (
            (activated_norm.notna())
            & (activated_norm <= current_date)
            & (~done_mask)  # ensure done items are not counted as in progress
        )

        todo_mask = ~done_mask & ~in_progress_mask

        done_count = done_mask.sum()
        in_progress_count = in_progress_mask.sum()
        todo_count = todo_mask.sum()

        # Append row
        cfd_data.append({
            "Date": current_date,
            "Done": int(done_count),
            "In Progress": int(in_progress_count),
            "To Do": int(todo_count)
        })

    cfd_df = pd.DataFrame(cfd_data)

    fig_cfd = px.area(
        cfd_df,
        x="Date",
        y=["Done", "In Progress", "To Do"],
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
    # Prepare normalized dates and effort column
    workitems_df["ActivatedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ActivatedDate"), utc=True, errors="coerce")
    workitems_df["ClosedDate"] = pd.to_datetime(workitems_df.get("Microsoft_VSTS_Common_ClosedDate"), utc=True, errors="coerce")

    created_norm = workitems_df["System_CreatedDate"].dt.normalize()
    activated_norm = workitems_df["ActivatedDate"].dt.normalize()
    closed_norm = workitems_df["ClosedDate"].dt.normalize()

    # Normalized min/max for range
    min_date = created_norm.min()
    max_date = pd.concat([created_norm, activated_norm, closed_norm]).max()

    date_range = pd.date_range(start=min_date, end=max_date + pd.Timedelta(days=1), freq="D")

    cfd_data = []

    # For numeric operations ensure effort is numeric (NaN -> 0 for sums)
    effort_series = pd.to_numeric(workitems_df.get(effort_field), errors="coerce").fillna(0)

    for current_date in date_range:
        done_mask = (closed_norm.notna()) & (closed_norm <= current_date)

        in_progress_mask = (
            (activated_norm.notna())
            & (activated_norm <= current_date)
            & (~done_mask)  # ensure done items are not counted as in progress
        )

        # Sum effort per state
        done_effort = effort_series[done_mask].sum(skipna=True)
        in_progress_effort = effort_series[in_progress_mask].sum(skipna=True)
        total_effort = effort_series.sum(skipna=True)
        todo_effort = total_effort - done_effort - in_progress_effort

        # Guard against tiny negative float rounding
        if todo_effort < 0 and todo_effort > -1e-8:
            todo_effort = 0.0

        cfd_data.append({
            "Date": current_date,
            "Done": float(done_effort),
            "In Progress": float(in_progress_effort),
            "To Do": float(todo_effort)
        })

    cfd_df = pd.DataFrame(cfd_data)

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
# ESTIMATE ACCURACY
# ---------------------------------------------
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

valid_estimates = workitems_df["EstimateAccuracy"].dropna()
active_time_indicator = valid_estimates.mean() if not valid_estimates.empty else None

last_iter_path = latest_iteration["path"]
last_iter_items = workitems_df[workitems_df["System_IterationPath"] == last_iter_path]
last_iter_estimates = last_iter_items["EstimateAccuracy"].dropna()
active_time_indicator_last_sprint = last_iter_estimates.mean() if not last_iter_estimates.empty else None

last_iter_name = last_iter_path.split("\\")[-1]

st.subheader("Active time ratio indicator (Cycle Time / Story Points)")
col1, col2 = st.columns(2)

with col1:
    st.metric(
        label="Overall Active time ratio indicator (All User Stories)",
        value=f"{active_time_indicator:.2f} %" if active_time_indicator else "N/A"
    )

with col2:
    st.metric(
        label=f"Active time ratio indicator (Last Iteration: {last_iter_name})",
        value=f"{active_time_indicator_last_sprint:.2f} %" if active_time_indicator_last_sprint else "N/A"
    )

# ---------------------------------------------
# AI INSIGHTS
# ---------------------------------------------
st.subheader("💬 AI Insights")

try:
    api_key = st.secrets["google"]["api_key"]
except KeyError:
    st.error("API Key not found in Streamlit secrets. Please ensure it's named 'GEMINI_API_KEY'.")
    st.stop()

# Configure Gemini
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')  # or 'gemini-2.5-pro'

# -------------------------
# AI Input Form
# -------------------------
with st.form(key="ai_insights_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        temp_team_size = st.number_input(
            label="Team Size",
            min_value=1,
            value=5,
            step=1
        )
    
    with col2:
        temp_capacity_per_person = st.number_input(
            label="Capacity per Person",
            min_value=1,
            value=8,
            step=1
        )
    
    submit = st.form_submit_button("🧠 Generate AI Analysis")

# -------------------------
# Trigger AI only after form submit
# -------------------------
if submit:
    # Assign committed values to session_state
    st.session_state["team_size"] = temp_team_size
    st.session_state["capacity_per_person"] = temp_capacity_per_person

    # Number of iterations
    num_iterations = len(iterations_df)

    # Build base metrics summary
    metrics_summary = {
        "Overall lead time": overall_lead_time,
        "Recent lead time (last 30 days)": recent_lead_time,
        "Overall cycle time": overall_cycle_time,
        "Recent cycle time (last 30 days)": recent_cycle_time,
        "Overall active time indicator": active_time_indicator,
        "Recent active time indicator": active_time_indicator_last_sprint,
        "Last iteration": latest_iteration["path"],
        "Iteration count": num_iterations,
        "Workitem count": len(workitems_df),
        "Team size": st.session_state["team_size"],
        "Capacity per person per iteration": st.session_state["capacity_per_person"],
    }

    # Include effort-based CFD metrics if available
    if 'cfd_df' in locals() and not cfd_df.empty:
        last_row = cfd_df.iloc[-1]
        total_done_effort = last_row["Done"]
        total_in_progress_effort = last_row["In Progress"]
        total_todo_effort = last_row["To Do"]

        # Average daily throughput (Done effort per day)
        daily_done_diff = cfd_df["Done"].diff().dropna()
        avg_daily_throughput = daily_done_diff.mean() if not daily_done_diff.empty else 0
        avg_per_iteration_throughput = total_done_effort / num_iterations if num_iterations else 0
        

        metrics_summary.update({
            "Total effort done": total_done_effort,
            "Total in progress effort": total_in_progress_effort,
            "Total effort to be done": total_todo_effort,
            "Average daily throughput (effort done per day)": avg_daily_throughput,
            "Average throughput (effort done per Iteration)": avg_per_iteration_throughput
        })

    # -------------------------
    # Send to AI
    # -------------------------
    with st.spinner("Analyzing metrics..."):
        prompt = f"""
        You are an Agile performance analyst.
        Here are key delivery metrics for a software team:

        {metrics_summary}

        Provide a short, data-driven summary of:
        - Performance trends (lead time, cycle time)
        - Bottlenecks or issues (based on CFD and team capacity, active time indicator)
        - Recommendations for improvement (actions, workshops, etc.)
        Be brief, concise. If data is unclear, make sure to note that too.
        The paradigm for capacity and effort is 1 capacity (day) is 1 effort (story point), with fibbonacci in mind (effort is estimated in 1, 2, 3, 5, 8, 13, 21+)
        """

        response = model.generate_content(prompt)
        st.markdown(response.text)

# ---------------------------------------------
# DETAILS SECTION
# ---------------------------------------------
with st.expander("See data details"):
    st.write("### Latest Iteration")
    st.dataframe(latest_iteration.to_frame().T)

    st.write("### Work Items Sample")
    st.dataframe(workitems_df.head())

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

    def load_work_items():
        work_items = list(workitems_col.find({"ops_user": user_email}, {"_id": 0}))
        if not work_items:
            return None, "No work items found in MongoDB. Please refresh."
        return work_items, None

    work_items, error_message = load_work_items()

    if error_message:
        st.warning(error_message)
    else:
        st.write(f"Total Work Items: {len(work_items)}")
        if isinstance(work_items, list) and all(isinstance(i, dict) for i in work_items):
            df = pd.DataFrame(work_items)
            st.dataframe(df)
        else:
            st.json(work_items)
