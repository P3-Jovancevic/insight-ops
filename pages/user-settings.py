import streamlit as st
import bcrypt
import re
from pymongo import MongoClient
import secrets

MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

if st.session_state["logged_in"]:
    st.subheader(f"User {st.session_state['user_email']} is logged in")
    if st.button("Sign out"):
        st.session_state["logged_in"] = False
        st.session_state["user_email"] = None
        st.rerun()
else:
    st.error("You are not logged in. Go to login page.")
    st.stop()