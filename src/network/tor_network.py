import socket
import threading
import requests
from requests.adapters import HTTPAdapter
from time import perf_counter, sleep
from urllib3.util.retry import Retry

from src.config import settings as config

_TOR_SESSION_LOCK = threading.Lock()
_TOR_SESSION = None

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - test environments may not install streamlit
    class _StreamlitFallback:
        @staticmethod
        def cache_resource(func):
            return func

    st = _StreamlitFallback()


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
            total=2,
            backoff_factor=0.4,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "POST", "PUT", "DELETE"],
        ),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
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


def make_request(url, method="GET", timeout=15, telemetry_callback=None, engine_name=None, **kwargs):
    """Make an HTTP request through Tor while emitting explicit telemetry for failures."""
    session = get_tor_session()
    request_name = engine_name or url

    def emit(phase, latency_ms, payload_bytes, status_icon, detail=""):
        if telemetry_callback is not None:
            telemetry_callback(request_name, phase, latency_ms, payload_bytes, status_icon, detail)

    emit("DNS Resolution", 0.0, 0, "🔄", "Initiating request")
    start_time = perf_counter()

    def _do_request(attempts_remaining=2):
        nonlocal start_time
        try:
            response = session.request(method.upper(), url, timeout=(5, timeout), **kwargs)
            elapsed_ms = (perf_counter() - start_time) * 1000.0
            payload_bytes = len(getattr(response, "content", b"") or b"")

            if response.status_code >= 400:
                error_phrase = (response.text or "").lower()
                if "no more hsdir available to query" in error_phrase or "hsdir" in error_phrase:
                    print(f"[Tor Network] HSDir failure detected for {url}, resetting session and retrying...")
                    reset_tor_session()
                    if attempts_remaining > 1:
                        sleep(1)
                        return _do_request(attempts_remaining - 1)

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
            emit("Socket Timeout", elapsed_ms, 0, "❌", f"Timed out after {timeout}s")
            print(f"[Tor Network] ⏱️ Timeout ({timeout}s) on {url}: {exc}")
            return None
        except requests.exceptions.ConnectionError as exc:
            elapsed_ms = (perf_counter() - start_time) * 1000.0
            message = str(exc).lower()
            if "hsdir" in message or "no more hsdir available to query" in message:
                print(f"[Tor Network] HSDir connection error detected for {url}, resetting session and retrying...")
                reset_tor_session()
                if attempts_remaining > 1:
                    sleep(1)
                    return _do_request(attempts_remaining - 1)
            emit("Socket Timeout", elapsed_ms, 0, "❌", str(exc))
            print(f"[Tor Network] Connection error on {url}: {exc}")
            return None
        except Exception as exc:
            elapsed_ms = (perf_counter() - start_time) * 1000.0
            message = str(exc).lower()
            if "hsdir" in message or "no more hsdir available to query" in message:
                print(f"[Tor Network] HSDir internal error detected for {url}, resetting session and retrying...")
                reset_tor_session()
                if attempts_remaining > 1:
                    sleep(1)
                    return _do_request(attempts_remaining - 1)
            emit("Socket Timeout", elapsed_ms, 0, "❌", str(exc))
            print(f"[Tor Network] Error on {url}: {exc}")
            return None

    return _do_request()