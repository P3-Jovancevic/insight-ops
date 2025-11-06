import streamlit as st
import pymongo
import bcrypt
import re
from modules.hide_pages import hide_internal_pages

# ---------------------------------------------
# HIDE PAGES FROM NAV
# ---------------------------------------------
hide_internal_pages()

# Connect to MongoDB Atlas
MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

st.set_page_config(page_title="Reset Password", layout="centered")
st.title("Reset Password")

# Extract token from URL
query_params = st.query_params
verification_token = query_params.get("token", None)

# Initialize session state for login
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_email"] = None

if verification_token:
    user = users_collection.find_one({"verification_token": verification_token})
    if user:
        email = user["email"]
        st.write(f"You are resetting the password for the account with the {email} email address.")
        
        with st.form("reset_password_form"):
            new_password = st.text_input("New password", type="password")
            confirm_password = st.text_input("Confirm new password", type="password")
            submit_button = st.form_submit_button("Reset Password")
        
        if submit_button:
            if not new_password or not confirm_password:
                st.error("All fields are required!")
            elif new_password != confirm_password:
                st.warning("Passwords do not match!")
            else:
                # Hash new password
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # Update user password in DB and remove verification token
                users_collection.update_one(
                    {"email": email},
                    {"$set": {"password": hashed_password}, "$unset": {"verification_token": ""}}
                )
                
                st.success("Password successfully changed!")
              
                if st.button("Home"):
                    st.switch_page("home.py")
                    st.rerun()
                    
    else:
        st.error("Invalid or expired reset token.")
else:
    st.write("Did you forget your password? Reset your password from the 'Forgot Password' page.")
    if st.button("Go to Forgot Password"):
        st.switch_page("pages/forgot-password.py")
