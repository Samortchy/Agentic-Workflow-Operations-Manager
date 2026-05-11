"""
ssl_patch.py — disable SSL certificate verification for Windows dev environments.

Import this as the very first line of any entry-point script (api.py, worker.py,
email_poller.py). The patch must run before any HTTP client is instantiated.

This mirrors NODE_TLS_REJECT_UNAUTHORIZED=0 that was added to the Node backend.
Do NOT use in production.
"""

import os
import ssl
import warnings

# Suppress the InsecureRequestWarning flood in logs
warnings.filterwarnings("ignore", message="Unverified HTTPS request")
os.environ.setdefault("PYTHONHTTPSVERIFY", "0")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "")
os.environ.setdefault("CURL_CA_BUNDLE", "")

# ── stdlib ssl ────────────────────────────────────────────────────────────────
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]

# ── requests / urllib3 ────────────────────────────────────────────────────────
try:
    import urllib3
    urllib3.disable_warnings()

    from requests.adapters import HTTPAdapter

    _orig_send = HTTPAdapter.send

    def _patched_send(self, request, **kwargs):
        kwargs["verify"] = False
        return _orig_send(self, request, **kwargs)

    HTTPAdapter.send = _patched_send
except Exception:
    pass

# ── httpx (used by Groq SDK) ──────────────────────────────────────────────────
try:
    import httpx

    _orig_client = httpx.Client.__init__

    def _patched_client(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        _orig_client(self, *args, **kwargs)

    httpx.Client.__init__ = _patched_client  # type: ignore[method-assign]

    _orig_async = httpx.AsyncClient.__init__

    def _patched_async(self, *args, **kwargs):
        kwargs.setdefault("verify", False)
        _orig_async(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = _patched_async  # type: ignore[method-assign]
except Exception:
    pass
