import streamlit as st

GEMINI_API_KEY = st.secrets.get("GOOGLE_API_KEY", "")
MAPS_API_KEY = st.secrets.get("MAPS_API_KEY", "")