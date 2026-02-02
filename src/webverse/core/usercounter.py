from __future__ import annotations

import json
import os
import platform
import threading
import time
from typing import Dict, Optional
from urllib import error, request

from webverse import __version__


API_URL = os.getenv("WEBVERSE_TELEMETRY_URL", "https://api-opensource.webverselabs.com/v1/telemetry")
TIMEOUT = float(os.getenv("WEBVERSE_TELEMETRY_TIMEOUT", "3") or 3)
DEBUG = (os.getenv("WEBVERSE_TELEMETRY_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"})


def _log(msg: str) -> None:
    if not DEBUG:
        return
    try:
        print(f"[telemetry] {msg}")
    except Exception:
        pass


def _post(body: bytes) -> None:
    req = request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"WebVerse-OSS/{__version__}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=TIMEOUT) as resp:
        code = getattr(resp, "status", None) or resp.getcode()
        if int(code) >= 400:
            _log(f"server returned HTTP {code}")

def send_event(name: str, props: Optional[Dict] = None, *, sync: bool = False) -> None:
    """Fire-and-forget anonymous telemetry.

    - Never blocks UI
    - Never raises
    - Does not transmit flags or sensitive content
    """
    try:
        # Lazy import to avoid circular dependency at module import time
        from webverse.core.progress_db import get_device_id
        device_id = get_device_id()
    except Exception as e:
        device_id = None
        _log(f"get_device_id failed: {e!r}")

    payload = {
        "device_id": device_id,
        "event": name,
        "timestamp": int(time.time()),
        "props": {
            "app_version": __version__,
            "platform": platform.system().lower(),
            **(props or {}),
        },
    }

    body = json.dumps(payload).encode("utf-8")

    if sync:
        # IMPORTANT: used for shutdown flush. Daemon threads often die before completing.
        try:
            _post(body)
        except error.HTTPError as e:
            _log(f"HTTPError: {e.code} {e.reason}")
        except Exception as e:
            _log(f"send failed: {e!r}")
        return

    def _send_bg() -> None:
        try:
            _post(body)
        except error.HTTPError as e:
            _log(f"HTTPError: {e.code} {e.reason}")
        except Exception as e:
            _log(f"send failed: {e!r}")

    threading.Thread(target=_send_bg, daemon=True).start()


def send_app_first_seen() -> None:
    """Send app_first_seen once per device."""
    try:
        from webverse.core import progress_db
        if progress_db.get_first_seen_sent():
            return
        send_event("app_first_seen", {})
        progress_db.set_first_seen_sent(True)
    except Exception as e:
        _log(f"first_seen failed: {e!r}")


def send_app_seen() -> None:
    """Heartbeat while the app is running."""
    send_event("app_seen", {})


def send_app_closed() -> None:
    """Best-effort event when the app closes."""
    send_event("last_closed_app", {}, sync=True)