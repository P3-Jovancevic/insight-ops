import streamlit as st
import pymongo
from pymongo import MongoClient
import bcrypt
import re
import secrets
from pages.send_verification_email import send_verification_email

# Connect to MongoDB Atlas
MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

st.set_page_config(page_title="Login & Register", layout="centered")

st.title("Welcome to InsightOps")

# Tabs for Login and Registration
selected_tab = st.radio("Select an option", ["Login", "Register"], horizontal=True)

if selected_tab == "Login":
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")

elif selected_tab == "Register":
    st.subheader("Register")
    with st.form("register_form"):
        new_username = st.text_input("Choose a Username")
        new_email = st.text_input("Email")
        new_password = st.text_input("Choose a Password", type="password", key="new_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
    
        # Real-time password match check
        if new_password and confirm_password and new_password != confirm_password:
            st.warning("Passwords do not match!")
        
        # Submit form
        submit_button = st.form_submit_button("Register")
    
    if submit_button:
        # Ensure all fields are filled
        if not new_username or not new_email or not new_password or not confirm_password:
            st.error("All fields are required!")
        else:
            # Validate email format
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if not re.match(email_pattern, new_email):
                st.error("Invalid email format! Please enter a valid email address.")
            elif new_password != confirm_password:
                st.error("Passwords do not match!")
            elif users_collection.find_one({"email": new_email}):
                st.error("This email is already registered!")
            elif users_collection.find_one({"username": new_username}):
                st.error("This username is already taken!")
            else:
                # Hash the password
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                
                # Generate verification token
                verification_token = secrets.token_urlsafe(32)
                
                # Insert new user into database
                users_collection.insert_one({
                    "username": new_username,
                    "email": new_email,
                    "password": hashed_password.decode('utf-8'),
                    "verified": False,
                    "verification_token": verification_token
                })
                
                st.success("Registration successful! A verification email will be sent.")

                send_verification_email(new_email, verification_token)