import streamlit as st

import streamlit as st

st.markdown(
    """
    <style>
    [data-testid="stSidebarNav"] {display: none;}
    </style>
    """,
    unsafe_allow_html=True
)

# Define the main page
def main_page():
    st.title("Welcome to Streamlit")
    if st.button("Go to Login/Register"):
        st.session_state.page = "login-register"

# Define the login-register page
def login_register_page():
    st.title("Login/Register")
    st.write("This is the login/register page.")

# Initialize session state
if 'page' not in st.session_state:
    st.session_state.page = "main"

# Render the appropriate page based on session state
if st.session_state.page == "main":
    main_page()
else:
    login_register_page()