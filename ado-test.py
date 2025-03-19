import requests

personal_access_token = "8GVUhWRIylouMfcXKvTt4porJQRRhirPHGYs6qDJqSOrZdJfeC50JQQJ99BCACAAAAAs05tvAAASAZDO3QES"
organization_url = "https://dev.azure.com/p3ds"
headers = {"Content-Type": "application/json"}

response = requests.get(
    f"{organization_url}/_apis/projects?api-version=7.0",
    auth=("", personal_access_token),
    headers=headers,
)

print(response.status_code, response.json())
