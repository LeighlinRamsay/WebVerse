import os
import json
import time
import secrets
from datetime import datetime
from urllib.parse import urlparse

import requests
from flask import Flask, request, make_response, redirect, render_template, abort

DOMAIN = os.getenv("LAB_DOMAIN", "harborledger.local").lower()
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev")
OPS_KEY = os.getenv("OPS_KEY", "opk_key_random_value_unguessable_bhbsjjmnshfd")
FILES_TOKEN = os.getenv("FILES_TOKEN", "ftk_dev_key_randome_value_unguessable_nbwhfegfdjksd")
FLAG = os.getenv("FLAG", "WEBVERSE{0ps_br1dg3_bec4m3_4n_3xp0rt_d00r}")

app = Flask(__name__)
app.secret_key = SESSION_SECRET

# --- lightweight in-memory "db" ---
USERS = {
    # seeded demo account (not very useful, but realistic)
    "partner.demo@contoso.local": {"password": "Winter2026!", "role": "partner_readonly", "org": "Contoso Shipping"},
}

INVITES = {
    "HL-PARTNER-READONLY-7G2Q": {
        "code": "HL-PARTNER-READONLY-7G2Q",
        "type": "partner_readonly",
        "org": "Bayside Freight",
        "created": "2026-01-10",
    },
    "HL-FINANCE-MONTHEND-9K4M": {
        "code": "HL-FINANCE-MONTHEND-9K4M",
        "type": "partner_finance",
        "org": "Bayside Freight",
        "created": "2026-01-12",
    },
    "HL-VENDOR-CLAIMS-2P9J": {
        "code": "HL-VENDOR-CLAIMS-2P9J",
        "type": "vendor_claims",
        "org": "Dockside Claims",
        "created": "2026-01-12",
    },
}

SESSIONS = {}  # sid -> email

# --- /ops rate limiting + temporary bans (in-memory) ---
# Rule: if an IP makes > 5 requests in < 2 seconds to anything under /ops/,
# ban that IP for 5 seconds.
#
OPS_RL_WINDOW_SEC = 2.0
OPS_RL_MAX_REQ = 5
OPS_RL_BAN_SEC = 5.0
OPS_RL_STATE = {
    # ip -> {"hits": [ts, ...], "ban_until": float}
}

EXPORT_DIR = "/tmp/exports"
os.makedirs(EXPORT_DIR, exist_ok=True)


def _host() -> str:
    return (request.host.split(":")[0] or "").lower()


def _subdomain() -> str:
    h = _host()
    suffix = "." + DOMAIN
    if h.endswith(suffix):
        return h[: -len(suffix)]
    return ""


def _session_email():
    sid = request.cookies.get("hl_session")
    if not sid:
        return None
    return SESSIONS.get(sid)


def _session_user():
    email = _session_email()
    if not email:
        return None
    return USERS.get(email)


def _require_login():
    if not _session_user():
        return redirect(f"http://auth.{DOMAIN}/login", code=302)
    return None


def _render(template_name: str, **kwargs):
    u = _session_user()
    return render_template(
        template_name,
        session_email=_session_email(),
        session_role=(u["role"] if u else None),
        **kwargs,
    )

def _client_ip() -> str:
    # Keep it simple for a local lab: use remote_addr.
    # (If you later add a reverse-proxy, you can optionally respect X-Forwarded-For.)
    return request.remote_addr or "unknown"

def _enforce_ops_rate_limit():
    """
    Apply rate limiting + temporary bans to any request under /ops/ on the API surface.
    Trigger:
      - path starts with /ops (covers /ops and /ops/*)
      - subdomain == api
    Rule:
      - > 5 requests within 2 seconds => ban 5 seconds
    """
    if _subdomain() != "api":
        return None
    if not (request.path == "/ops" or request.path.startswith("/ops/")):
        return None

    ip = _client_ip()
    now = time.time()

    st = OPS_RL_STATE.get(ip)
    if not st:
        st = {"hits": [], "ban_until": 0.0}
        OPS_RL_STATE[ip] = st

    # If currently banned, block immediately
    if st["ban_until"] > now:
        retry = max(0.0, st["ban_until"] - now)
        resp = make_response({"error": "rate_limited", "detail": "temporary ban", "retry_after": round(retry, 2)}, 429)
        resp.headers["Retry-After"] = str(int(retry) + 1)
        resp.headers["X-RateLimit-Policy"] = f"ops>{OPS_RL_MAX_REQ}/{OPS_RL_WINDOW_SEC}s ban={OPS_RL_BAN_SEC}s"
        return resp

    # Slide window
    cutoff = now - OPS_RL_WINDOW_SEC
    st["hits"] = [t for t in st["hits"] if t >= cutoff]
    st["hits"].append(now)

    # If exceeded, ban and block this request
    if len(st["hits"]) > OPS_RL_MAX_REQ:
        st["ban_until"] = now + OPS_RL_BAN_SEC
        resp = make_response({"error": "rate_limited", "detail": "temporary ban", "retry_after": round(OPS_RL_BAN_SEC, 2)}, 429)
        resp.headers["Retry-After"] = str(int(OPS_RL_BAN_SEC) + 1)
        resp.headers["X-RateLimit-Policy"] = f"ops>{OPS_RL_MAX_REQ}/{OPS_RL_WINDOW_SEC}s ban={OPS_RL_BAN_SEC}s"
        return resp

    return None


@app.before_request
def enforce_surfaces():
    # single container, but we only "serve" these subdomains
    sd = _subdomain()
    if sd not in {"portal", "auth", "api", "files"}:
        # allow bare domain (optional)
        if _host() == DOMAIN:
            return
        abort(404)

    # /ops rate limiting + temporary bans (API surface only)
    rl = _enforce_ops_rate_limit()
    if rl is not None:
        return rl


# -------------------- PORTAL --------------------
@app.get("/")
def portal_index():
    if _subdomain() not in {"portal", ""}:
        abort(404)
    return _render("portal_index.html", title="HarborLedger")


@app.get("/go")
def portal_go():
    if _subdomain() != "portal":
        abort(404)
    nxt = request.args.get("next", "/")

    if not nxt:
        return {"error": "missing next parameter"}, 500
    # Open redirect (classic, "continue" handler)
    return redirect(nxt, code=302)


@app.get("/dashboard")
def portal_dashboard():
    if _subdomain() != "portal":
        abort(404)
    guard = _require_login()
    if guard:
        return guard
    user = _session_user()
    return _render("dashboard.html", title="Dashboard", org=user["org"], export_msg=None)


@app.post("/exports/request")
def portal_export_request():
    if _subdomain() != "portal":
        abort(404)
    guard = _require_login()
    if guard:
        return guard

    # This is intentionally "miswired" to a legacy ops bridge.
    # Users see a generic permission error that doesn't reveal too much.
    resp = make_response(
        _render(
            "dashboard.html",
            title="Dashboard",
            org=_session_user()["org"],
            export_msg="Export request failed.",
        ),
        403,
    )
    resp.headers["X-Trace-Reason"] = "OPS_SCOPE_REQUIRED"
    resp.headers["X-Gateway"] = "legacy-ops-bridge"
    return resp


@app.get("/imports")
def portal_imports():
    if _subdomain() != "portal":
        abort(404)
    guard = _require_login()
    if guard:
        return guard
    user = _session_user()
    if user["role"] != "partner_admin":
        return make_response(
            _render("imports.html", title="Imports", error="Not available for your role.", result=None),
            403,
        )
    return _render("imports.html", title="Imports", error=None, result=None)


# -------------------- AUTH --------------------
@app.route("/login", methods=["GET", "POST"])
def auth_login():
    if _subdomain() != "auth":
        abort(404)
    if request.method == "GET":
        return _render("login.html", title="Sign in", error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    u = USERS.get(email)
    if not u or u["password"] != password:
        return _render("login.html", title="Sign in", error="Invalid credentials."), 401

    sid = secrets.token_urlsafe(24)
    SESSIONS[sid] = email
    resp = make_response(redirect(f"http://portal.{DOMAIN}/dashboard"))
    resp.set_cookie("hl_session", sid, httponly=True, samesite="Lax", domain="." + DOMAIN)
    return resp


@app.route("/invite/accept", methods=["GET", "POST"])
def auth_invite_accept():
    if _subdomain() != "auth":
        abort(404)

    if request.method == "GET":
        code = (request.args.get("code") or "").strip()
        invite = INVITES.get(code) if code else None
        return _render("invite_accept.html", title="Accept invite", invite=invite, error=None)

    code = (request.form.get("code") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    invite = INVITES.get(code)
    if not invite:
        return _render("invite_accept.html", title="Accept invite", invite=None, error="Invalid invite code."), 400

    if email in USERS:
        return _render("invite_accept.html", title="Accept invite", invite=invite, error="Email already registered."), 400

    # Misconfigured invite-role mapping (business logic): finance partner invites grant admin in the partner portal.
    role = "partner_readonly"
    if invite["type"] == "partner_finance":
        role = "partner_admin"

    USERS[email] = {"password": password, "role": role, "org": invite["org"]}

    sid = secrets.token_urlsafe(24)
    SESSIONS[sid] = email
    resp = make_response(redirect(f"http://portal.{DOMAIN}/dashboard"))
    resp.set_cookie("hl_session", sid, httponly=True, samesite="Lax", domain="." + DOMAIN)
    return resp


@app.get("/logout")
def portal_logout():
    if _subdomain() != "portal":
        abort(404)
    sid = request.cookies.get("hl_session")
    if sid and sid in SESSIONS:
        del SESSIONS[sid]
    resp = make_response(redirect(f"http://portal.{DOMAIN}/"))
    resp.delete_cookie("hl_session", domain="." + DOMAIN)
    return resp


# -------------------- API --------------------
@app.post("/api/v1/import/url")
def api_import_url():
    if _subdomain() != "api":
        abort(404)
    user = _session_user()
    if not user:
        return {"error": "unauthenticated"}, 401
    if user["role"] != "partner_admin":
        return {"error": "forbidden"}, 403

    url = ""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        url = data.get("url") or ""
    else:
        url = request.form.get("url") or ""

    url = (url or "").strip()
    if not url:
        return {"error": "missing url"}, 400

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    allowed_hosts = {f"portal.{DOMAIN}", f"files.{DOMAIN}"}
    if host not in allowed_hosts:
        return {"error": "url host rejected"}, 400

    try:
        r = requests.get(url, timeout=3, allow_redirects=True)
        body = r.text
        if len(body) > 4000:
            body = body[:4000] + "\n..."
        return {
            "fetched": True,
            "final_url": r.url,
            "status": r.status_code,
            "body": body,
        }
    except Exception as e:
        return {"error": "fetch failed", "detail": str(e)}, 502

@app.get("/ops")
@app.get("/ops/")
def ops_root_probe():
    """
    Discovery affordance:
    If a player hits the API subdomain at /ops (with no specific endpoint),
    return a clear 403 so they learn 'ops' paths exist (and can fuzz deeper).

    Important:
    - Only exists on the API surface.
    - Does NOT replace /ops/* behavior (those endpoints still enforce X-Ops-Key).
    """
    if _subdomain() != "api":
        abort(404)
    return {"error": "forbidden"}, 403


@app.get("/internal/ops/keys")
def api_internal_ops_keys():
    if _subdomain() != "api":
        abort(404)

    # localhost-only: meant for sidecar health checks / internal bridge
    if request.remote_addr not in {"127.0.0.1", "::1"}:
        return {"error": "forbidden"}, 403

    return {
        "service": "ops-bridge",
        "issued_at": datetime.utcnow().isoformat() + "Z",
        "ops_key": OPS_KEY,
        "note": "rotated during month-end (see diagnostics)",
    }


@app.get("/ops/diagnostics")
def api_ops_diagnostics():
    if _subdomain() != "api":
        abort(404)

    key = request.headers.get("X-Ops-Key") or request.headers.get("Ops-Key") or ""
    if key != OPS_KEY:
        return {"error": "unauthorized", "details": "Missing Ops Header"}, 401

    # Insecure logging: secret tokens printed into diagnostics.
    logs = [
        "[ops] bridge=legacy route=/ops/export month=2026-01",
        f"[ops] exporter -> files: header X-Files-Token: {FILES_TOKEN}",
        f"[ops] files endpoint: http://files.{DOMAIN}/internal/exports/generate",
        "[ops] note: exports are stored under /exports/<id>.csv",
    ]
    return {"service": "ops-bridge", "logs": logs}


# -------------------- FILES --------------------
@app.route("/internal/exports/generate", methods=["GET", "POST"])
def files_generate_export():
    if _subdomain() != "files":
        abort(404)

    tok = request.headers.get("X-Files-Token") or ""
    if tok != FILES_TOKEN:
        return {"error": "unauthorized"}, 401

    month = (request.form.get("month") or "2026-01").strip()
    export_id = secrets.token_hex(6)
    path = os.path.join(EXPORT_DIR, f"{export_id}.csv")

    rows = [
        ["org", "month", "total_fees", "variance"],
        ["Bayside Freight", month, "18420.11", "-312.44"],
        ["Dockside Claims", month, "4920.00", "0.00"],
        ["notes", "executive_recon", "internal_only", FLAG],
    ]

    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(",".join(r) + "\n")

    return {
        "generated": True,
        "export_id": export_id,
    }


@app.get("/exports/<export_id>.csv")
def files_download_export(export_id: str):
    if _subdomain() != "files":
        abort(404)

    path = os.path.join(EXPORT_DIR, f"{export_id}.csv")
    if not os.path.exists(path):
        return {"error": "not found"}, 404

    with open(path, "r", encoding="utf-8") as f:
        data = f.read()

    resp = make_response(data)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
