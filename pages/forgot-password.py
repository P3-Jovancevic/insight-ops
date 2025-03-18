import streamlit as st
import pymongo
import secrets
from modules.send_forgot_password_email import send_forgot_password_email  # Assuming this function sends emails

# Connect to MongoDB
MONGODB_URI = st.secrets["mongo"]["uri"]
DATABASE_NAME = "insightops"
COLLECTION_NAME = "users"
client = pymongo.MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
users_collection = db[COLLECTION_NAME]

st.set_page_config(page_title="Password Recovery", layout="centered")
st.title("Password Recovery")
st.write("Enter your email. A password recovery email will be sent to your email.")

email = st.text_input("Email")

if st.button("Change Password"):
    if not email:
        st.error("Please enter your email.")
    else:
        user = users_collection.find_one({"email": email})
        if user:
            # Generate new verification token
            verification_token = secrets.token_urlsafe(32)
            users_collection.update_one({"email": email}, {"$set": {"verification_token": verification_token}})
            
            # Send verification email
            verification_link = f"{st.secrets['app']['base_url']}/reset-password?token={verification_token}"
            send_forgot_password_email(new_email, verification_token)
            
            st.success("If this email is registered, a password reset link has been sent.")
        else:
            st.error("No account found with that email.")
