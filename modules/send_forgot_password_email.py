import smtplib
from email.mime.text import MIMEText
import streamlit as st

def send_forgot_password_email(user_email, verification_token):
    smtp_server = st.secrets["google_smtp"]["server"]
    smtp_port = st.secrets["google_smtp"]["port"]
    sender_email = st.secrets["google_smtp"]["email"]
    sender_password = st.secrets["google_smtp"]["password"]
    
    verification_link = f"https://insight-ops.streamlit.app/reset-password?token={verification_token}"
    subject = "InsightOps - Password reset"
    body = f"If you did not make a reset password request, ignore this email. To reset your password, follow this link: {verification_link}"
    
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = user_email
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, user_email, msg.as_string())
        print("Reset password email sent successfuly.")
    except Exception as e:
        print(f"Failed to send email: {e}")
