import streamlit as st
import pymongo
import pandas as pd

MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "sample_mflix"
COLLECTION_NAME = "users"

try:
    client = pymongo.MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]
    count = collection.count_documents({})
    print(f"Document count: {count}")
    client.admin.command('ping')
    print("Connection successful")

    # Fetch all documents from the collection
    documents = list(collection.find())

    # Convert documents to a Pandas DataFrame
    df = pd.DataFrame(documents)

    # Display the DataFrame in Streamlit
    st.write("Documents from the collection:")
    st.dataframe(df)

except pymongo.errors.PyMongoError as e:
    print(f"Error: {e}")
    st.error(f"Error: {e}") #show error in streamlit also.