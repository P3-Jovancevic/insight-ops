import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
from pymongo import MongoClient

# -------------------------------------------------------------
# MongoDB connection
# -------------------------------------------------------------
mongo_uri = st.secrets["mongo"]["uri"]
db_name = st.secrets["mongo"]["db_name"]

client = MongoClient(mongo_uri)
db = client[db_name]
iterations_col = db["ado-iterations"]
workitems_col = db["ado-workitems"]

st.subheader("📈 Burn-Up Chart")

# -------------------------------------------------------------
# Metric toggle (Story Count / Effort Points)
# -------------------------------------------------------------
metric_option = st.radio(
    "Select metric for Burn-Up:",
    ["Story Count", "Effort Points"],
    horizontal=True,
)

# -------------------------------------------------------------
# Load data from MongoDB
# -------------------------------------------------------------
iterations = list(iterations_col.find({}, {"path": 1, "startDate": 1, "finishDate": 1, "_id": 0}))
workitems = list(workitems_col.find({}, {
    "System_IterationPath": 1,
    "Microsoft_VSTS_Common_ClosedDate": 1,
    "System_CreatedDate": 1,
    "StoryPoints": 1,  # assuming field name for effort
    "_id": 0
}))

if not iterations or not workitems:
    st.warning("No iteration or work item data found in MongoDB.")
    st.stop()

# Convert to DataFrames
df_iter = pd.DataFrame(iterations)
df_items = pd.DataFrame(workitems)

# Convert dates to UTC datetime
for col in ["startDate", "finishDate"]:
    df_iter[col] = pd.to_datetime(df_iter[col], utc=True, errors="coerce")

for col in ["System_CreatedDate", "Microsoft_VSTS_Common_ClosedDate"]:
    df_items[col] = pd.to_datetime(df_items[col], utc=True, errors="coerce")

# -------------------------------------------------------------
# Calculate total and completed items per iteration
# -------------------------------------------------------------
burnup_data = []

for _, it_row in df_iter.iterrows():
    iteration_path = it_row["path"]
    start_date = it_row["startDate"]
    finish_date = it_row["finishDate"]

    if pd.isna(start_date) or pd.isna(finish_date):
        continue

    # Filter work items belonging to this iteration
    it_items = df_items[df_items["System_IterationPath"] == iteration_path]

    if metric_option == "Story Count":
        total = len(it_items)
        completed = len(it_items[it_items["Microsoft_VSTS_Common_ClosedDate"].notna()])
    else:
        # Sum of effort points
        total = it_items["StoryPoints"].fillna(0).sum()
        completed = it_items.loc[it_items["Microsoft_VSTS_Common_ClosedDate"].notna(), "StoryPoints"].fillna(0).sum()

    burnup_data.append({
        "Iteration": iteration_path,
        "FinishDate": finish_date,
        "Total": total,
        "Completed": completed
    })

df_burnup = pd.DataFrame(burnup_data).sort_values(by="FinishDate")

# Cumulative values across iterations
df_burnup["CumulativeTotal"] = df_burnup["Total"].cumsum()
df_burnup["CumulativeCompleted"] = df_burnup["Completed"].cumsum()

# -------------------------------------------------------------
# Plot Burn-Up Chart
# -------------------------------------------------------------
fig = px.line(
    df_burnup,
    x="FinishDate",
    y=["CumulativeTotal", "CumulativeCompleted"],
    markers=True,
    labels={"value": metric_option, "FinishDate": "Iteration Finish Date", "variable": "Metric"},
    title=f"Burn-Up Chart ({metric_option})"
)

fig.update_traces(mode="lines+markers")
fig.update_layout(
    legend_title_text="",
    xaxis_title="Iteration Finish Date",
    yaxis_title=metric_option,
    hovermode="x unified"
)

st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------------------
# Optional Data Table
# -------------------------------------------------------------
with st.expander("📊 Show Burn-Up Data Table"):
    st.dataframe(df_burnup, use_container_width=True)
