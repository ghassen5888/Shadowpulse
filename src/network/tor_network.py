import socket
import threading
import logging
import traceback
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from time import perf_counter
from urllib3.util.retry import Retry

from src.config import settings as config

_TOR_SESSION_LOCK = threading.Lock()
_TOR_SESSION = None
LOGGER = logging.getLogger(__name__)

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - test environments may not install streamlit
    class _StreamlitFallback:
        @staticmethod
        def cache_resource(func):
            return func

    st = _StreamlitFallback()


class TorResolutionError(requests.exceptions.ConnectionError):
    """Raised when Tor reports hidden-service resolution/connectivity failure."""


_TOR_RESOLUTION_ERROR_MARKERS = (
    "no more hsdir available to query",
    "hsdir",
    "host unreachable",
    "socks",
    "failed to establish a new connection",
    "name or service not known",
    "temporary failure in name resolution",
)


def is_tor_resolution_error(error):
    message = str(error or "").lower()
    return any(marker in message for marker in _TOR_RESOLUTION_ERROR_MARKERS)


def _build_tor_session():
    session = requests.Session()
    session.trust_env = False
    session.proxies = {
        "http": f"socks5h://{config.TOR_PROXY_IP}:{config.TOR_PORT}",
        "https": f"socks5h://{config.TOR_PROXY_IP}:{config.TOR_PORT}",
    }
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }
    )

    adapter = HTTPAdapter(
        pool_connections=100,
        pool_maxsize=100,
        pool_block=False,
        max_retries=Retry(
            total=0,
            connect=0,
            read=0,
            redirect=0,
            status=0,
            other=0,
            backoff_factor=0.0,
            allowed_methods=False,
        ),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    proxy_url = f"socks5h://{config.TOR_PROXY_IP}:{config.TOR_PORT}"
    LOGGER.debug("[SHADOWPULSE DEBUG] [TOR NETWORK] SOCKS5 proxy configured proxy=%s", proxy_url)
    print("[Tor Network] Cached session created with connection pooling enabled.")
    return session


def get_tor_session():
    """Return a shared Tor-enabled HTTP session, building it on demand."""
    global _TOR_SESSION
    with _TOR_SESSION_LOCK:
        if _TOR_SESSION is None:
            _TOR_SESSION = _build_tor_session()
        return _TOR_SESSION


def reset_tor_session():
    """Reset the cached Tor session to force a new circuit on the next request."""
    global _TOR_SESSION
    with _TOR_SESSION_LOCK:
        if _TOR_SESSION is not None:
            try:
                _TOR_SESSION.close()
            except Exception:
                pass
            _TOR_SESSION = None


def setup_tor():
    """Verify that the Tor daemon is reachable on the configured proxy port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
            result = test_socket.connect_ex((config.TOR_PROXY_IP, config.TOR_PORT))
        if result == 0:
            print("✅ Tor Port (9050) is Open")
            return True
        print("❌ Tor Port (9050) is Closed. Is Tor running?")
        return False
    except Exception as exc:
        print(f"[Network] Tor check error: {exc}")
        return False


def make_request(url, method="GET", timeout=15, telemetry_callback=None, engine_name=None, raise_on_error=False, **kwargs):
    """Make an HTTP request through Tor while emitting explicit telemetry for failures."""
    session = get_tor_session()
    request_name = engine_name or url
    if isinstance(timeout, tuple):
        connect_timeout, read_timeout = timeout
        timeout_label = f"{connect_timeout}/{read_timeout}s"
        request_timeout = (connect_timeout, read_timeout)
    else:
        connect_timeout, read_timeout = 5, timeout
        timeout_label = f"{timeout}s"
        request_timeout = (connect_timeout, read_timeout)

    def emit(phase, latency_ms, payload_bytes, status_icon, detail=""):
        if telemetry_callback is not None:
            telemetry_callback(request_name, phase, latency_ms, payload_bytes, status_icon, detail)

    emit("DNS Resolution", 0.0, 0, "🔄", "Initiating request")
    start_time = perf_counter()

    try:
        request_ts = perf_counter()
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [TOR NETWORK] request_start method=%s url=%s timestamp=%s perf_ts=%.6f timeout=%s",
            method.upper(),
            url,
            datetime.now().isoformat(),
            request_ts,
            timeout_label,
        )
        response = session.request(method.upper(), url, timeout=request_timeout, **kwargs)
        elapsed_ms = (perf_counter() - start_time) * 1000.0
        payload_bytes = len(getattr(response, "content", b"") or b"")
        LOGGER.debug(
            "[SHADOWPULSE DEBUG] [TOR NETWORK] request_success method=%s url=%s status_code=%s duration_s=%.3f response_chars=%d",
            method.upper(),
            url,
            response.status_code,
            elapsed_ms / 1000.0,
            len(response.text or ""),
        )

        if response.status_code >= 400:
            error_phrase = (response.text or "").lower()
            if is_tor_resolution_error(error_phrase):
                resolution_error = TorResolutionError(f"Tor resolution failed for {url}: HTTP {response.status_code}")
                emit("Tor Resolution Failed", elapsed_ms, 0, "❌", str(resolution_error))
                if raise_on_error:
                    raise resolution_error
                return None

            emit("Completed", elapsed_ms, payload_bytes, "❌", f"HTTP {response.status_code}")
            print(f"[Tor Network] HTTP {response.status_code} for {url}")
            return response

        emit("Handshake", elapsed_ms * 0.35, 0, "🔄", "Proxy negotiation")
        emit("Connected", elapsed_ms * 0.6, 0, "🔄", f"HTTP {response.status_code}")
        emit("Streaming Payload", elapsed_ms * 0.9, payload_bytes, "✅", f"Received {payload_bytes} bytes")
        emit("Completed", elapsed_ms, payload_bytes, "✅", f"HTTP {response.status_code}")
        return response
    except requests.exceptions.Timeout as exc:
        elapsed_ms = (perf_counter() - start_time) * 1000.0
        emit("Socket Timeout", elapsed_ms, 0, "❌", f"Timed out after {timeout_label}")
        LOGGER.error(
            "[SHADOWPULSE DEBUG] [TOR NETWORK] request_error category=Timeout method=%s url=%s duration_s=%.3f error=%s",
            method.upper(),
            url,
            elapsed_ms / 1000.0,
            exc,
        )
        LOGGER.error(traceback.format_exc())
        print(f"[Tor Network] ⏱️ Timeout ({timeout_label}) on {url}: {exc}")
        if raise_on_error:
            raise
        return None
    except requests.exceptions.ProxyError as exc:
        elapsed_ms = (perf_counter() - start_time) * 1000.0
        emit("Tor Resolution Failed", elapsed_ms, 0, "❌", str(exc))
        LOGGER.error(
            "[SHADOWPULSE DEBUG] [TOR NETWORK] request_error category=ProxyError method=%s url=%s duration_s=%.3f error=%s",
            method.upper(),
            url,
            elapsed_ms / 1000.0,
            exc,
        )
        LOGGER.error(traceback.format_exc())
        resolution_error = TorResolutionError(str(exc))
        if raise_on_error:
            raise resolution_error from exc
        return None
    except requests.exceptions.ConnectionError as exc:
        elapsed_ms = (perf_counter() - start_time) * 1000.0
        emit("Tor Resolution Failed", elapsed_ms, 0, "❌", str(exc))
        LOGGER.error(
            "[SHADOWPULSE DEBUG] [TOR NETWORK] request_error category=ConnectionError method=%s url=%s duration_s=%.3f error=%s",
            method.upper(),
            url,
            elapsed_ms / 1000.0,
            exc,
        )
        LOGGER.error(traceback.format_exc())
        print(f"[Tor Network] Connection error on {url}: {exc}")
        resolution_error = TorResolutionError(str(exc))
        if raise_on_error:
            raise resolution_error from exc
        return None
    except Exception as exc:
        elapsed_ms = (perf_counter() - start_time) * 1000.0
        emit("Socket Timeout", elapsed_ms, 0, "❌", str(exc))
        LOGGER.error(
            "[SHADOWPULSE DEBUG] [TOR NETWORK] request_error category=Unhandled method=%s url=%s duration_s=%.3f error=%s",
            method.upper(),
            url,
            elapsed_ms / 1000.0,
            exc,
        )
        LOGGER.error(traceback.format_exc())
        print(f"[Tor Network] Error on {url}: {exc}")
        if is_tor_resolution_error(exc):
            resolution_error = TorResolutionError(str(exc))
            if raise_on_error:
                raise resolution_error from exc
            return None
        if raise_on_error:
            raise
        return None