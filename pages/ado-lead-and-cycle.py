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
# DATABASE CONNECTION
# ---------------------------------------------
mongo_uri = st.secrets["mongo"]["uri"]
client = MongoClient(mongo_uri)
db = client["insight-ops"]

# ---------------------------------------------
# LOAD DATA FROM MONGODB
# ---------------------------------------------
iterations_collection = db["ado-iterations"]
workitems_collection = db["ado-workitems"]

iterations = list(iterations_collection.find())
workitems = list(workitems_collection.find())

if not iterations or not workitems:
    st.warning("No iteration or work item data found.")
    st.stop()

iterations_df = pd.DataFrame(iterations)
workitems_df = pd.DataFrame(workitems)

# ---------------------------------------------
# DATA PREPARATION
# ---------------------------------------------
iterations_df["startDate"] = pd.to_datetime(iterations_df["startDate"], errors="coerce")
iterations_df["finishDate"] = pd.to_datetime(iterations_df["finishDate"], errors="coerce")

workitems_df["System_CreatedDate"] = pd.to_datetime(workitems_df["System_CreatedDate"], errors="coerce")
workitems_df["Microsoft_VSTS_Common_ClosedDate"] = pd.to_datetime(workitems_df["Microsoft_VSTS_Common_ClosedDate"], errors="coerce")

# ---------------------------------------------
# FILTER RELEVANT WORK ITEM TYPES
# ---------------------------------------------
allowed_types = ["User Story", "PBI", "Product Backlog Item"]
workitems_df = workitems_df[workitems_df["System_WorkItemType"].isin(allowed_types)]

# ---------------------------------------------
# LEAD TIME & CYCLE TIME CALCULATION
# ---------------------------------------------
now = datetime.now(timezone.utc)
closed_filled_for_lead = workitems_df["Microsoft_VSTS_Common_ClosedDate"].fillna(pd.Timestamp(now))
lead_timedelta = closed_filled_for_lead - workitems_df["System_CreatedDate"]
workitems_df["LeadTimeDays"] = lead_timedelta.dt.days

workitems_df = workitems_df.merge(
    iterations_df[["path", "startDate", "finishDate"]],
    left_on="System_IterationPath",
    right_on="path",
    how="left"
)

closed_filled_for_cycle = workitems_df["Microsoft_VSTS_Common_ClosedDate"].fillna(pd.Timestamp(now))
cycle_timedelta = closed_filled_for_cycle - workitems_df["startDate"]
workitems_df["CycleTimeDays"] = cycle_timedelta.dt.days

# ---------------------------------------------
# LEAD & CYCLE TIME AVERAGES BY ITERATION
# ---------------------------------------------
lead_cycle_summary = workitems_df.groupby("System_IterationPath", as_index=False).agg({
    "LeadTimeDays": "mean",
    "CycleTimeDays": "mean"
})
lead_cycle_summary = lead_cycle_summary.round(1)

# ---------------------------------------------
# BURN-UP CALCULATION (STORY COUNT)
# ---------------------------------------------
burnup_data = []
for _, iteration in iterations_df.iterrows():
    iteration_path = iteration["path"]
    iteration_end = iteration["finishDate"]
    iteration_items = workitems_df[workitems_df["System_IterationPath"] == iteration_path]

    total_stories = len(iteration_items)
    completed_stories = len(iteration_items[
        iteration_items["Microsoft_VSTS_Common_ClosedDate"] <= iteration_end
    ])

    burnup_data.append({
        "Iteration": iteration_path,
        "EndDate": iteration_end,
        "TotalStories": total_stories,
        "CompletedStories": completed_stories
    })

burnup_df = pd.DataFrame(burnup_data)

# ---------------------------------------------
# BURN-UP CALCULATION (EFFORT-BASED)
# ---------------------------------------------
effort_field = None
for candidate in ["Microsoft_VSTS_Scheduling_Effort", "StoryPoints", "Effort"]:
    if candidate in workitems_df.columns:
        effort_field = candidate
        break

if effort_field:
    burnup_effort_data = []
    for _, iteration in iterations_df.iterrows():
        iteration_path = iteration["path"]
        iteration_end = iteration["finishDate"]
        iteration_items = workitems_df[workitems_df["System_IterationPath"] == iteration_path]

        total_effort = iteration_items[effort_field].sum(skipna=True)
        completed_effort = iteration_items.loc[
            iteration_items["Microsoft_VSTS_Common_ClosedDate"] <= iteration_end, effort_field
        ].sum(skipna=True)

        burnup_effort_data.append({
            "Iteration": iteration_path,
            "EndDate": iteration_end,
            "TotalEffort": total_effort,
            "CompletedEffort": completed_effort
        })

    burnup_effort_df = pd.DataFrame(burnup_effort_data)
else:
    burnup_effort_df = pd.DataFrame()

# ---------------------------------------------
# DISPLAY METRICS
# ---------------------------------------------
st.subheader("Average Lead & Cycle Time per Iteration")
st.dataframe(lead_cycle_summary, use_container_width=True)

# ---------------------------------------------
# BURN-UP CHART (STORY COUNT)
# ---------------------------------------------
st.subheader("Burn-Up Chart (Story Count)")
fig_story = px.line(
    burnup_df,
    x="EndDate",
    y=["CompletedStories", "TotalStories"],
    markers=True,
    labels={
        "EndDate": "Iteration End Date",
        "value": "Number of Stories",
        "variable": "Metric"
    },
    title="Burn-Up Progress by Iteration (Stories)"
)
# Add iteration labels
for i, row in burnup_df.iterrows():
    fig_story.add_annotation(
        x=row["EndDate"],
        y=row["CompletedStories"],
        text=row["Iteration"].split("\\")[-1],
        showarrow=False,
        yshift=10
    )

st.plotly_chart(fig_story, use_container_width=True)

# ---------------------------------------------
# BURN-UP CHART (EFFORT-BASED)
# ---------------------------------------------
if not burnup_effort_df.empty:
    st.subheader(f"Burn-Up Chart ({effort_field}-Based)")
    fig_effort = px.line(
        burnup_effort_df,
        x="EndDate",
        y=["CompletedEffort", "TotalEffort"],
        markers=True,
        labels={
            "EndDate": "Iteration End Date",
            "value": f"Total {effort_field}",
            "variable": "Metric"
        },
        title=f"Burn-Up Progress by Iteration ({effort_field})"
    )
    # Add iteration labels
    for i, row in burnup_effort_df.iterrows():
        fig_effort.add_annotation(
            x=row["EndDate"],
            y=row["CompletedEffort"],
            text=row["Iteration"].split("\\")[-1],
            showarrow=False,
            yshift=10
        )

    st.plotly_chart(fig_effort, use_container_width=True)
else:
    st.info("No effort-based field found (e.g., StoryPoints or Effort).")

