import streamlit as st
import pymongo
from pymongo import MongoClient
import bcrypt
import re
import secrets
from datetime import datetime
from modules.send_verification_email import send_verification_email

# Connect to MongoDB Atlas
MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

st.set_page_config(page_title="Login & Register", layout="centered")

st.title("Welcome to InsightOps")

# Initialize session state for login
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None

if st.session_state["logged_in"]:
    st.subheader(f"User {st.session_state['user_email']} is logged in")
    if st.button("Sign out"):
        st.session_state["logged_in"] = False
        st.session_state["user_email"] = None
        st.rerun()
else:
    # Tabs for Login and Registration
    selected_tab = st.radio("Select an option", ["Login", "Register"], horizontal=True)

    if selected_tab == "Login":
        st.subheader("Login")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            st.markdown("[Forgot Password?](https://insight-ops.streamlit.app/forgot-password)")
            submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if not email or not password:
                st.error("All fields are required!")
            else:
                user = users_collection.find_one({"email": email})
                if user and bcrypt.checkpw(password.encode('utf-8'), user["password"].encode('utf-8')):
                    if user.get("verified"):
                        st.session_state["logged_in"] = True
                        st.session_state["user_email"] = email
                        st.success("Login successful! Welcome back.")
                        st.rerun()
                    else:
                        st.error("Your account is not verified. Please check your email.")
                else:
                    st.error("Invalid email or password.")

    elif selected_tab == "Register":
        st.subheader("Register")
        with st.form("register_form"):
            new_username = st.text_input("Choose a Username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Choose a Password", type="password", key="new_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
            
            submit_button = st.form_submit_button("Register")
        
        if submit_button:
            errors = []

            # Normalize inputs
            new_email = new_email.strip().lower()

            # Validate fields
            if not new_username or not new_email or not new_password or not confirm_password:
                errors.append("All fields are required.")

            # Email format check
            email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
            if new_email and not re.match(email_pattern, new_email):
                errors.append("Invalid email format.")

            # Password match
            if new_password != confirm_password:
                errors.append("Passwords do not match.")

            # Uniqueness checks
            if users_collection.find_one({"email": new_email}):
                errors.append("This email is already registered.")
            elif users_collection.find_one({"username": new_username}):
                errors.append("This username is already taken.")

            # Show errors or proceed
            if errors:
                for error in errors:
                    st.error(error)
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
                    "verification_token": verification_token,
                    "organization_url": "",
                    "project_name": "",
                    "pat": "",
                    "updated_at": datetime.utcnow(),
                    "created_at": datetime.utcnow()
                })

                # Send verification email
                verification_link = f"{st.secrets['app']['base_url']}/verify?token={verification_token}"
                send_verification_email(new_email, verification_token)

                st.success("Registration successful! A verification email has been sent.")
