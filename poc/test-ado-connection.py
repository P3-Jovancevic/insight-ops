import requests
import streamlit as st

# Get credentials from secrets
personal_access_token = st.secrets["ado"]["ado_pat"]
organization_url = st.secrets["ado"]["ado_site"]

# Define headers
headers = {
    "Content-Type": "application/json"
}

# Send request to Azure DevOps REST API
response = requests.get(
    f"{organization_url}/_apis/projects?api-version=7.0",
    auth=("", personal_access_token),
    headers=headers,
)

# Output result in Streamlit app
st.write("Status Code:", response.status_code)
st.write("Response JSON:", response.json())
