"""Streamlit entrypoint for Shadowpulse dashboard."""

from dotenv import load_dotenv

load_dotenv()

from src.ui import dashboard  # noqa: F401
