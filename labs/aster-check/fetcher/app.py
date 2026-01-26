import traceback
from flask import Flask, request, jsonify, make_response, abort
import os, hmac, hashlib, sys
from urllib.parse import urlparse
import requests

app = Flask(__name__)

SIGNING_KEY = "WEBVERSE{51GN3D_URL5_D0N7_H1D3_53CR375}"

INTERNAL_HOST_MAP = {
    "reports.astercheck.local": "http://reports:8000",
    "canary-astercode-development.astercheck.local": "http://canary_code:8000",
    "app.astercheck.local": "http://app:8000",
    "astercheck.local": "http://app:8000",
}

PASS_HEADERS = {"content-type", "set-cookie", "location", "Set-Cookie", "Location", "Content-Type"}

def _hmac_sig(url: str) -> str:
    return hmac.new(SIGNING_KEY.encode(), url.encode(), hashlib.sha256).hexdigest()

def _rewrite_internal(url: str) -> str:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host in INTERNAL_HOST_MAP:
        base = INTERNAL_HOST_MAP[host].rstrip("/")
        path = u.path or "/"
        qs = f"?{u.query}" if u.query else ""
        return f"{base}{path}{qs}"
    return url

def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code

@app.route("/api/v1/fetch", methods=["GET", "POST", "HEAD"])
def fetch():
    try:
        if request.method == "GET":
            url = request.args.get("url", "")
            sig = request.args.get("sig", "")
            method = "GET"
            fwd_headers = {}
            body = None
            json_body = None
        else:
            data = request.get_json(force=True)  # force JSON; if it's not JSON you'll get a clean 400 below
            if not isinstance(data, dict):
                return _bad("invalid json body")

            url = data.get("url", "")
            sig = data.get("sig", "")
            method = data.get("method", "")
            if not method:
                return jsonify({"error": "Missing method or headers key"}), 500

            fwd_headers = data.get("headers", {})
            body = data.get("body", None)
            json_body = data.get("json", None)

        # ---- Strict type checks (prevents 500s) ----
        if not isinstance(url, str) or not url.strip():
            return _bad("missing url")
        if not isinstance(sig, str) or not sig.strip():
            return _bad("missing sig")

        url = url.strip()
        sig = sig.strip()

        if not isinstance(method, str):
            return _bad("invalid method")
        method = method.strip().upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            return _bad("method not allowed", 405)

        if not isinstance(fwd_headers, dict):
            return _bad("headers must be an object")

        u = urlparse(url)
        if u.scheme not in ("http", "https"):
            return _bad("invalid scheme")

        expected = _hmac_sig(url)
        if not hmac.compare_digest(expected, sig):
            return _bad("invalid signature", 403)

        host = (u.hostname or "").lower()
        if host.endswith(".astercheck.local") and host not in INTERNAL_HOST_MAP:
            return jsonify({"error": "unknown internal host"}), 502

        real_url = _rewrite_internal(url)

        # Ensure UA always present
        ua_present = any(k.lower() == "user-agent" for k in fwd_headers.keys())
        if not ua_present:
            fwd_headers["User-Agent"] = request.headers.get("User-Agent", "AsterCheckFetch/2.4.8")

        # Body handling: keep bytes if we can
        data_body = None
        if body is not None:
            if isinstance(body, str):
                data_body = body.encode("utf-8", errors="ignore")
            elif isinstance(body, (bytes, bytearray)):
                data_body = bytes(body)
            else:
                # if someone sent a non-string, don't explode
                data_body = str(body).encode("utf-8", errors="ignore")

        r = requests.request(
            method=method,
            url=real_url,
            headers=fwd_headers,
            data=body if body is not None else None,
            json=json_body if json_body is not None else None,
            timeout=5,
            allow_redirects=False,
        )

        # ---- LAB DEBUG: if upstream is not 2xx, return a JSON debug envelope
        '''if r.status_code >= 500:
            ct = r.headers.get("Content-Type", "")
            text_preview = ""
            try:
                # try to decode text-ish bodies; otherwise just show length
                text_preview = r.text
            except Exception:
                text_preview = f"<non-text body length={len(r.content)}>"

            return jsonify({
                "error": "upstream_error",
                "upstream_status": r.status_code,
                "upstream_url": url,
                "rewritten_url": real_url,
                "upstream_content_type": ct,
                "upstream_headers": {k: v for k, v in r.headers.items() if k.lower() in PASS_HEADERS or k.lower() == "content-type"},
                "upstream_body": text_preview,
            }), r.status_code

            return jsonify({"error": "internal error"}), 500'''

        # ---- Normal successful pass-through for 2xx/3xx
        resp = make_response(r.content, r.status_code)

        for k, v in r.headers.items():
            if k.lower() in PASS_HEADERS:
                resp.headers[k] = v

        if "Content-Type" not in resp.headers:
            resp.headers["Content-Type"] = r.headers.get("Content-Type", "text/plain; charset=utf-8")

        return resp

    except Exception as e:
        '''# ---- LAB DEBUG: return full traceback in response
        tb = traceback.format_exc()
        print("FETCHER EXCEPTION:", tb, file=sys.stderr, flush=True)
        return jsonify({
            "error": "fetch_exception",
            "message": str(e),
            "upstream_url": url,
            "rewritten_url": real_url,
            "traceback": tb,
        }), 500'''

        return jsonify({"error": "internal error"}), 500

# MAIN signed fetch endpoint
@app.get("/api/v2/fetch")
def fetch_main():
    url = (request.args.get("url") or "").strip()
    sig = (request.args.get("sig") or "").strip()

    if not url or not sig:
        return jsonify({"error": "missing url or sig"}), 400

    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return jsonify({"error": "invalid scheme"}), 400

    expected = _hmac_sig(url)
    if not hmac.compare_digest(expected, sig):
        return jsonify({"error": "invalid signature"}), 403

    # allow internal fetch by rewriting known internal hosts to docker service names
    real_url = _rewrite_internal(url)

    # Unknown internal hostnames should still be "fuzzable" (return meaningful failure)
    host = (u.hostname or "").lower()
    if host.endswith(".astercheck.local") and host not in INTERNAL_HOST_MAP:
        return jsonify({"error": "unknown internal host"}), 502

    try:
        r = requests.get(real_url, timeout=4, allow_redirects=False, headers={
            "User-Agent": request.headers.get("User-Agent", "AsterCheckFetch/2.4.8"),
        })
        resp = make_response(r.content, r.status_code)
        resp.headers["Content-Type"] = r.headers.get("Content-Type", "text/plain; charset=utf-8")
        return resp
    except Exception:
        return jsonify({"error": "fetch failed"}), 502

'''@app.errorhandler(Exception)
def handle_any_exception(e):
    print("=== GLOBAL EXCEPTION ===", file=sys.stderr, flush=True)
    traceback.print_exc()
    return jsonify({"error": "internal error"}), 500'''

@app.get("/")
def root():
    return jsonify({"status": "Fetcher API v2 healthy"})

@app.get("/api/")
def api_root():
    abort(403)

@app.get("/api/v1/")
def v1_root():
    abort(403)

@app.get("/api/v2/")
def v2_root():
    abort(403)

# Legacy v1 signing oracle (intended discovery)
@app.get("/api/v1/sign")
def sign_v1():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "missing url"}), 400

    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return jsonify({"error": "invalid scheme"}), 400

    return jsonify({"url": url, "sig": _hmac_sig(url), "note": "legacy endpoint - should be removed"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)