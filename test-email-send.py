import streamlit as st
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load email credentials from secrets
EMAIL_ADDRESS = st.secrets["google_smtp"]["email"]
EMAIL_PASSWORD = st.secrets["google_smtp"]["password"]
SMTP_SERVER = st.secrets["google_smtp"]["server"]
SMTP_PORT = st.secrets["google_smtp"]["port"]

def send_test_email():
    recipient_email = st.text_input("Enter recipient email")
    subject = "Test Email from Streamlit"
    body = "This is a test email sent from Streamlit using Google SMTP."

    if st.button("Send Test Email"):
        try:
            # Create email
            msg = MIMEMultipart()
            msg["From"] = EMAIL_ADDRESS
            msg["To"] = recipient_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            # Connect to SMTP server
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
                smtp.starttls()  # Secure connection
                smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                smtp.sendmail(EMAIL_ADDRESS, recipient_email, msg.as_string())

            st.success(f"Test email sent successfully to {recipient_email}")

        except Exception as e:
            st.error(f"Failed to send email: {e}")

# Run test function in Streamlit
send_test_email()
