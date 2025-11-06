import streamlit as st

def hide_internal_pages():
    st.markdown("""
        <style>
        section[data-testid="stSidebar"] ul li a[href*="forgot-password"],
        section[data-testid="stSidebar"] ul li a[href*="reset-password"],
        section[data-testid="stSidebar"] ul li a[href*="verify"] {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
