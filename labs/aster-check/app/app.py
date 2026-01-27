from flask import Flask, render_template, request
import os
import hmac
import hashlib
from urllib.parse import urlparse
import requests

app = Flask(__name__)

# inside docker, fetcher is reachable by service name
FETCH_BASE = "http://fetcher:8000"

# must match fetcher SIGNING_KEY, but the UI signs internally (no /api/v1/sign calls)
SIGNING_KEY = "WEBVERSE{51GN3D_URL5_D0N7_H1D3_53CR375}"

BLOCKED_SUFFIX = ".astercheck.local"

def _hmac_sig(url: str) -> str:
    return hmac.new(SIGNING_KEY.encode(), url.encode(), hashlib.sha256).hexdigest()

def _is_blocked_target(url: str) -> bool:
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower().strip(".")
        if not host:
            return True
        # Block all internal subdomains from the official UI
        if host == "astercheck.local" or host.endswith(BLOCKED_SUFFIX):
            return True
        return False
    except Exception:
        return True

def _validate_public_url(url: str):
    if not isinstance(url, str) or not url.strip():
        return False, "Enter a URL to preview."
    url = url.strip()

    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return False, "Only http(s) URLs are allowed."

    if _is_blocked_target(url):
        return False, "That host is not allowed for previews."

    return True, url

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/preview")
def preview():
    raw = request.form.get("url", "")
    ok, url_or_err = _validate_public_url(raw)
    if not ok:
        return render_template("index.html", error=url_or_err)

    url = url_or_err

    # Sign internally (NO request to /api/v1/sign)
    sig = _hmac_sig(url)

    try:
        r = requests.get(
            f"{FETCH_BASE}/api/v2/fetch",
            params={"url": url, "sig": sig},
            timeout=6,
            allow_redirects=False,
            headers={
                # keep it realistic; fetcher may pass this along
                "User-Agent": request.headers.get("User-Agent", "AsterCheckUI/1.0")
            },
        )

        # Show a “preview” even on non-200, but in a controlled way
        ct = r.headers.get("Content-Type", "text/plain; charset=utf-8")

        # Don’t try to render binary blobs into HTML
        body_preview = ""
        try:
            body_preview = r.text
        except Exception:
            body_preview = f"<non-text body length={len(r.content)}>"

        return render_template(
            "index.html",
            result=body_preview,
            status=r.status_code,
            content_type=ct,
            preview_url=url,
        )

    except Exception as e:
        return render_template("index.html", error="Preview failed.", result=str(e))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
