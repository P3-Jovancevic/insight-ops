import streamlit as st

import streamlit as st

# Define the main page
def main_page():
    st.title("Welcome to Streamlit")
    if st.button("Go to Login/Register"):
        st.session_state.page = "login-register"