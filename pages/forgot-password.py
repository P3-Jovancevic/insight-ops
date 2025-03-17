import streamlit as st
import pymongo
import secrets
from send_verification_email import send_email  # Assuming this function sends emails

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
            
            # Send password reset email
            reset_url = f"{st.secrets['app']['base_url']}/change-password?token={verification_token}"
            send_email(email, "Password Reset Request", f"Click here to reset your password: {reset_url}")
            
            st.success("If this email is registered, a password reset link has been sent.")
        else:
            st.error("No account found with that email.")
