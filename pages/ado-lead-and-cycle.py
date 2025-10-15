import streamlit as st
from pymongo import MongoClient
import pandas as pd
from datetime import datetime, timedelta, timezone
import matplotlib.pyplot as plt

# ---------------------------------------------
# MongoDB connection
# ---------------------------------------------
mongo_uri = st.secrets["mongo"]["uri"]
client = MongoClient(mongo_uri)
db = client["insight-ops"]

iterations_col = db["ado-iterations"]
workitems_col = db["ado-workitems"]

# ---------------------------------------------
# Helper to parse dates consistently
# ---------------------------------------------
def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

# ---------------------------------------------
# Load data from MongoDB
# ---------------------------------------------
iterations = list(iterations_col.find({}, {"path": 1, "startDate": 1, "finishDate": 1, "_id": 0}))
workitems = list(workitems_col.find({}, {
    "System_Id": 1,
    "System_IterationPath": 1,
    "System_CreatedDate": 1,
    "Microsoft_VSTS_Common_ClosedDate": 1,
    "Microsoft_VSTS_Scheduling_Effort": 1,
    "_id": 0
}))

# Convert to DataFrames
df_iterations = pd.DataFrame(iterations)
df_workitems = pd.DataFrame(workitems)

# Parse dates
df_iterations["startDate"] = df_iterations["startDate"].apply(parse_date)
df_iterations["finishDate"] = df_iterations["finishDate"].apply(parse_date)
df_workitems["System_CreatedDate"] = df_workitems["System_CreatedDate"].apply(parse_date)
df_workitems["Microsoft_VSTS_Common_ClosedDate"] = df_workitems["Microsoft_VSTS_Common_ClosedDate"].apply(parse_date)

# ---------------------------------------------
# Burn-up chart preparation
# ---------------------------------------------
st.header("📈 Burn-up Chart")

# Choose metric: count or effort
metric_choice = st.radio(
    "Select metric for burn-up chart:",
    ["Story Count", "Effort Sum"],
    horizontal=True
)

burnup_data = []

for _, iteration in df_iterations.iterrows():
    iteration_path = iteration["path"]
    start_date = iteration["startDate"]
    finish_date = iteration["finishDate"]

    if not (start_date and finish_date):
        continue

    # Filter work items for this iteration
    items_in_iteration = df_workitems[df_workitems["System_IterationPath"] == iteration_path]

    # Compute total scope (based on selected metric)
    if metric_choice == "Effort Sum":
        total_scope = items_in_iteration["Microsoft_VSTS_Scheduling_Effort"].fillna(0).sum()
    else:
        total_scope = len(items_in_iteration)

    # Compute completed (closed before or on finish date)
    closed_items = items_in_iteration[
        items_in_iteration["Microsoft_VSTS_Common_ClosedDate"].notnull() &
        (items_in_iteration["Microsoft_VSTS_Common_ClosedDate"] <= finish_date)
    ]

    if metric_choice == "Effort Sum":
        completed = closed_items["Microsoft_VSTS_Scheduling_Effort"].fillna(0).sum()
    else:
        completed = len(closed_items)

    burnup_data.append({
        "Iteration": iteration_path,
        "StartDate": start_date,
        "FinishDate": finish_date,
        "TotalScope": total_scope,
        "Completed": completed
    })

# Convert to DataFrame
df_burnup = pd.DataFrame(burnup_data)

# ---------------------------------------------
# Plot Burn-up Chart
# ---------------------------------------------
if not df_burnup.empty:
    plt.figure(figsize=(10, 5))
    plt.plot(df_burnup["FinishDate"], df_burnup["TotalScope"], label="Total Scope", marker="o")
    plt.plot(df_burnup["FinishDate"], df_burnup["Completed"], label="Completed", marker="o")

    plt.title(f"Burn-up Chart ({metric_choice})")
    plt.xlabel("Iteration Finish Date")
    plt.ylabel("Count" if metric_choice == "Story Count" else "Effort (Sum)")
    plt.legend()
    plt.grid(True)
    st.pyplot(plt)
else:
    st.warning("No burn-up data available for visualization.")
