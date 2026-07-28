"""Streamlit entrypoint for Shadowpulse dashboard."""

import logging
import traceback

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s [SHADOWPULSE DEBUG] [%(name)s] %(message)s")

LOGGER = logging.getLogger(__name__)

try:
    from src.ui import dashboard  # noqa: F401
except Exception as exc:
    LOGGER.error("[SHADOWPULSE DEBUG] [APP] CRITICAL FAILURE: %s", str(exc))
    LOGGER.error(traceback.format_exc())
    raise
