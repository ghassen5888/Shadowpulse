"""Streamlit entrypoint for Shadowpulse dashboard."""

import logging

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

from src.ui import dashboard  # noqa: F401
