from __future__ import annotations

import io
import json
import os
import re
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from flask import (
    Flask,
    abort,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


def _utc_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def _lab_domain() -> str:
    return (os.getenv("LAB_DOMAIN", "arcadenal.local") or "arcadenal.local").strip().lower()


def _host_no_port() -> str:
    return (request.host or "").split(":")[0].strip().lower()

def surface_from_host(host: str, lab_domain: str) -> str:
    """
    Single-container multi-subdomain routing (no nginx):
    - arcadenal.local          -> root/marketing
    - blog.arcadenal.local     -> blog UI + debug search
    - portal.arcadenal.local   -> auth/dashboard/admin download
    - api.arcadenal.local      -> JSON API endpoints
    """
    h = (host or "").split(":")[0].strip().lower()
    ld = (lab_domain or "").strip().lower()
    if not ld:
        return "root"
    if h == f"blog.{ld}":
        return "blog"
    if h == f"portal.{ld}":
        return "portal"
    if h == f"api.{ld}":
        return "api"
    if h == ld:
        return "root"
    return "root"

def _redirect_surface(surface: str, lab_domain: str):
    surface = (surface or "root").strip().lower()
    ld = (lab_domain or "").strip().lower()
    if surface == "blog":
        host = f"blog.{ld}"
    elif surface == "portal":
        host = f"portal.{ld}"
    elif surface == "api":
        host = f"api.{ld}"
    else:
        host = ld

    scheme = request.scheme or "http"
    qs = request.query_string.decode(errors="ignore")
    url = f"{scheme}://{host}{request.path}"
    if qs:
        url += "?" + qs
    return redirect(url)


def _subdomain(lab_domain: str) -> str:
    host = _host_no_port()
    lab_domain = (lab_domain or "").strip().lower()
    if not lab_domain:
        return ""
    if host == lab_domain:
        return ""
    if host.endswith("." + lab_domain):
        return host[: -(len(lab_domain) + 1)]
    return ""


def _json_loads_loose(s: str) -> Any:
    # Intentionally loose: blog "debug search" tries to be helpful and accepts raw JSON.
    # If parsing fails, it falls back to treating it like a string search.
    try:
        return json.loads(s)
    except Exception:
        return s


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _db_path() -> Path:
    return Path(os.getenv("DB_PATH", "/data/arcadenal_db.json"))


def _seed_db() -> Dict[str, Any]:
    # Random admin password (not printed anywhere). Intended route is takeover via approvals.
    admin_pw = secrets.token_urlsafe(18)

    users = [
        {
            "username": "admin",
            "email": "admin@arcadenal.local",
            "password_hash": generate_password_hash(admin_pw, method="pbkdf2:sha256", salt_length=16),
            "role": "admin",
            "created_ts": _utc_ts() - 86400 * 19,
        },
        {
            "username": "maria",
            "email": "maria@arcadenal.local",
            "password_hash": generate_password_hash("NeverGonnaCrackThis!", method="pbkdf2:sha256", salt_length=16),
            "role": "user",
            "created_ts": _utc_ts() - 86400 * 7,
        },
    ]

    posts = [
        {
            "id": 1,
            "title": "Arcadenal Launch Week",
            "tags": ["arcade", "launch", "retro"],
            "author": "maria",
            "body": "Welcome to Arcadenal — where nostalgia meets web-scale.",
        },
        {
            "id": 2,
            "title": "Why approvals? (short answer: bots)",
            "tags": ["security", "approvals"],
            "author": "maria",
            "body": "We added approvals to stop account farming. What could go wrong?",
        },
    ]

    return {
        "users": users,
        "posts": posts,
        "approvals": [],
        "meta": {"seeded_ts": _utc_ts(), "build": "arcadenal-v1"},
    }


def _load_db() -> Dict[str, Any]:
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if (not p.exists()) or p.stat().st_size == 0:
        db = _seed_db()
        p.write_text(json.dumps(db, indent=2), encoding="utf-8")
        return db
    return json.loads(p.read_text(encoding="utf-8"))


def _save_db(db: Dict[str, Any]) -> None:
    _db_path().write_text(json.dumps(db, indent=2), encoding="utf-8")


def _find_user(db: Dict[str, Any], username: str) -> Dict[str, Any] | None:
    username = (username or "").strip().lower()
    for u in db.get("users", []):
        if (u.get("username") or "").strip().lower() == username:
            return u
    return None


def _upsert_user(db: Dict[str, Any], username: str, email: str, password_plain: str) -> Tuple[Dict[str, Any], bool]:
    """
    Intentionally dangerous upsert: if username exists, overwrite password hash.
    This is how approvals were "simplified" (and how takeovers happen).
    """
    username_n = (username or "").strip().lower()
    email = (email or "").strip()
    existing = _find_user(db, username_n)
    if existing is not None:
        existing["email"] = email or existing.get("email", "")
        existing["password_hash"] = generate_password_hash(password_plain, method="pbkdf2:sha256", salt_length=16)
        existing["updated_ts"] = _utc_ts()
        return existing, False

    u = {
        "username": username_n,
        "email": email,
        "password_hash": generate_password_hash(password_plain, method="pbkdf2:sha256", salt_length=16),
        "role": "user",
        "created_ts": _utc_ts(),
    }
    db.setdefault("users", []).append(u)
    return u, True


def _create_approval(db: Dict[str, Any], username: str, email: str, password_plain: str) -> Dict[str, Any]:
    token = secrets.token_urlsafe(24)
    req = {
        "token": token,
        "username": (username or "").strip().lower(),
        "email": (email or "").strip(),
        "password_plain": password_plain,  # yes... stored for "approval replay"
        "created_ts": _utc_ts(),
        "note": "pending-manual-approval",
    }
    db.setdefault("approvals", []).append(req)
    return req


# -----------------------------
# NoSQL-ish matcher (intentionally flawed)
# -----------------------------
def _match_value(value: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        for op, arg in cond.items():
            if op == "$ne":
                if value == arg:
                    return False
            elif op == "$regex":
                try:
                    if not re.search(str(arg), str(value or ""), re.IGNORECASE):
                        return False
                except Exception:
                    return False
            elif op == "$exists":
                want = bool(arg)
                exists = value is not None
                if want != exists:
                    return False
            else:
                return False
        return True
    return value == cond


def _matches(doc: Dict[str, Any], query: Any) -> bool:
    if not isinstance(query, dict):
        return False

    if "$or" in query and isinstance(query["$or"], list):
        for subq in query["$or"]:
            if isinstance(subq, dict) and _matches(doc, subq):
                return True
        return False

    for k, cond in query.items():
        if k == "$or":
            continue
        v = doc.get(k)
        if not _match_value(v, cond):
            return False
    return True


def _collection(db: Dict[str, Any], name: str) -> List[Dict[str, Any]]:
    # Intentionally trusts user input (debug endpoint).
    name = (name or "posts").strip().lower()
    col = db.get(name)
    if isinstance(col, list):
        return col
    return []


def _current_user(db: Dict[str, Any]) -> Dict[str, Any] | None:
    uname = session.get("username")
    if not uname:
        return None
    return _find_user(db, str(uname))


def _require_login(db: Dict[str, Any]) -> Dict[str, Any]:
    u = _current_user(db)
    if not u:
        abort(401)
    return u


def _is_admin(u: Dict[str, Any] | None) -> bool:
    return bool(u) and (u.get("role") or "").strip().lower() == "admin"


# -----------------------------
# App setup + routes
# -----------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "arcadenal-dev-secret")

@app.before_request
def _cookie_domain_config():
    # Make portal/api/blog share the same session cookie across subdomains,
    # like LinkLapse's .LAB_DOMAIN cookies.
    ld = _lab_domain()
    app.config["SESSION_COOKIE_DOMAIN"] = f".{ld}"
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = False


@app.after_request
def _hdrs(resp):
    resp.headers["Server"] = "Arcadenal"
    return resp


@app.route("/")
def index():
    db = _load_db()
    lab_domain = _lab_domain()
    surf = surface_from_host(request.host, lab_domain)

    if surf == "root":
        return render_template("marketing.html", domain=lab_domain)
    if surf == "blog":
        posts = db.get("posts", [])
        if not isinstance(posts, list):
            posts = []
        return render_template("blog_home.html", domain=lab_domain, posts=posts)
    if surf == "portal":
        u = _current_user(db)
        if u:
            return redirect(url_for("portal_dashboard"))
        return render_template("portal_login.html", domain=lab_domain, error=None)
    if surf == "api":
        abort(403)
    abort(404)

@app.route("/post/<int:post_id>")
def blog_post(post_id: int):
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "blog":
        return _redirect_surface("blog", lab_domain)

    db = _load_db()
    posts = db.get("posts", [])
    if not isinstance(posts, list):
        posts = []

    hit = None
    for p in posts:
        if isinstance(p, dict) and _safe_int(p.get("id"), -1) == int(post_id):
            hit = p
            break

    if not hit:
        abort(404)

    return render_template("blog_post.html", domain=lab_domain, post=hit)


@app.route("/robots.txt")
def robots():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "root":
        return _redirect_surface("root", lab_domain)
    return make_response("User-agent: *\nDisallow: /internal/\n", 200, {"Content-Type": "text/plain; charset=utf-8"})


@app.route("/backup.zip")
def backup_zip():
    """
    Exposed deployment backup. Contains partial API code with "REDACTED" for secrets.
    """
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "root":
        return _redirect_surface("root", lab_domain)

    api_code = f"""# api/server.py (partial backup)
# NOTE: values marked REDACTED were removed before sharing this archive internally.

LAB_DOMAIN = "{lab_domain}"
ADMIN_APPROVAL_REQUIRED = True

# Approvals are stored in collection: "approvals"
# Users are stored in collection: "users"

def register(db, username, email, password_plain):
    # TODO: block reserved usernames? (admin?)
    token = "REDACTED_GENERATED_TOKEN"
    db["approvals"].append({{
        "token": token,
        "username": username,
        "email": email,
        "password_plain": password_plain,
        "created_ts": 0
    }})
    return "submitted creation request, wait for admin to approve account"

def approve(db, token):
    req = find_one(db["approvals"], {{"token": token}})
    # upsert user on approval (simplifies onboarding)
    upsert(db["users"], {{"username": req["username"]}}, {{
        "$set": {{
            "email": req["email"],
            "password_hash": hash_pw(req["password_plain"]),
        }}
    }})
    delete_one(db["approvals"], {{"token": token}})
    return True

# blog debug search (used by content team)
# GET http://blog.{lab_domain}/api/search?collection=posts&q={{"tags":{{"$regex":"retro"}}}}
"""
    readme = """Arcadenal Internal Backup (sanitized)

This archive was meant for the content team to spin up local previews.
Sensitive values are replaced with REDACTED, but routes and data shapes remain.

Hint: approvals live in the "approvals" collection. The blog has a debug search used by the team.
"""

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("backup/README.txt", readme)
        z.writestr("backup/api/server.py", api_code)
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name="backup.zip", max_age=0)


# -----------------------------
# Portal pages (portal.<domain>)
# -----------------------------
@app.route("/portal/login", methods=["GET"])
def portal_login():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)
    return render_template("portal_login.html", domain=lab_domain, error=None)


@app.route("/portal/login", methods=["POST"])
def portal_login_post():
    db = _load_db()
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    u = _find_user(db, username)
    if (not u) or (not check_password_hash(str(u.get("password_hash") or ""), password)):
        return render_template("portal_login.html", domain=lab_domain, error="Invalid credentials.")
    session["username"] = username
    return redirect(url_for("portal_dashboard"))


@app.route("/portal/logout")
def portal_logout():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)
    session.clear()
    return redirect(url_for("index"))


@app.route("/portal/register", methods=["GET"])
def portal_register():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)
    return render_template("portal_register.html", domain=lab_domain, msg=None, err=None)


@app.route("/portal/register", methods=["POST"])
def portal_register_post():
    db = _load_db()
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)

    username = (request.form.get("username") or "").strip().lower()
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    if not username or not email or not password:
        return render_template("portal_register.html", domain=lab_domain, msg=None, err="Missing fields.")

    _create_approval(db, username, email, password)
    _save_db(db)

    msg = "Submitted creation request. Wait for admin approval."
    return render_template("portal_register.html", domain=lab_domain, msg=msg, err=None)


def _approve_token(db: Dict[str, Any], token: str) -> Tuple[bool, str]:
    approvals = db.get("approvals", [])
    hit = None
    for r in approvals:
        if str(r.get("token", "")).strip() == token:
            hit = r
            break
    if not hit:
        return False, "Token invalid or already used."

    username = str(hit.get("username") or "").strip().lower()
    email = str(hit.get("email") or "").strip()
    pw = str(hit.get("password_plain") or "")

    # Preserve role if the user already exists (e.g., admin takeover!)
    existing = _find_user(db, username)
    role = (existing.get("role") if existing else None) or "user"

    u, _created = _upsert_user(db, username, email, pw)
    u["role"] = role

    db["approvals"] = [r for r in approvals if r is not hit]
    return True, "Account approved. You may now log in."


@app.route("/portal/approve")
def portal_approve_page():
    db = _load_db()
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)
    token = (request.args.get("token") or "").strip()
    if not token:
        return render_template("portal_approve.html", domain=lab_domain, ok=False, detail="Missing token.")

    ok, detail = _approve_token(db, token)
    _save_db(db)
    return render_template("portal_approve.html", domain=lab_domain, ok=ok, detail=detail)


@app.route("/portal/dashboard")
def portal_dashboard():
    db = _load_db()
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)
    u = _require_login(db)
    return render_template("portal_dashboard.html", domain=lab_domain, user=u, is_admin=_is_admin(u))


@app.route("/portal/admin/download/tax-form")
def portal_tax_form():
    db = _load_db()
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "portal":
        return _redirect_surface("portal", lab_domain)
    u = _require_login(db)
    if not _is_admin(u):
        abort(403)

    flag = os.getenv("FLAG", "WEBVERSE{dummy_flag}")
    content = f"""Arcadenal Finance Export (Internal)

Quarterly Revenue Summary (Sanitized)
------------------------------------
Q1:  $13,337
Q2:  $42,000
Q3:  $9,001
Q4:  $88,888

Notes:
- Approval tokens were supposed to stop cheaters.
- Turns out... they ARE the cheater's quarters.

FLAG: {flag}
"""
    bio = io.BytesIO(content.encode("utf-8"))
    return send_file(bio, mimetype="application/octet-stream", as_attachment=True, download_name="arcadenal_tax_form_2025.txt", max_age=0)


# -----------------------------
# API endpoints (documented in backup)
# -----------------------------
@app.route("/api/v1/register", methods=["POST"])
def api_register():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "api":
        abort(404)
    db = _load_db()
    body = request.get_json(silent=True) or {}
    username = str(body.get("username") or "").strip().lower()
    email = str(body.get("email") or "").strip()
    password = str(body.get("password") or "")
    if not username or not email or not password:
        return jsonify({"ok": False, "error": "missing fields"}), 400

    req = _create_approval(db, username, email, password)
    _save_db(db)
    return jsonify({"ok": True, "message": "submitted creation request, wait for admin to approve account", "request_id": req["token"][:8]})


@app.route("/api/v1/approve", methods=["POST"])
def api_approve():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "api":
        abort(404)
    db = _load_db()
    body = request.get_json(silent=True) or {}
    token = str(body.get("token") or "").strip()
    ok, detail = _approve_token(db, token)
    _save_db(db)
    return jsonify({"ok": ok, "detail": detail})


@app.route("/api/v1/login", methods=["POST"])
def api_login():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "api":
        abort(404)
    db = _load_db()
    body = request.get_json(silent=True) or {}
    username = str(body.get("username") or "").strip().lower()
    password = str(body.get("password") or "")
    u = _find_user(db, username)
    if (not u) or (not check_password_hash(str(u.get("password_hash") or ""), password)):
        return jsonify({"ok": False, "error": "invalid credentials"}), 401
    session["username"] = username
    return jsonify({"ok": True, "role": u.get("role", "user")})


@app.route("/api/v1/me")
def api_me():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "api":
        abort(404)
    db = _load_db()
    u = _current_user(db)
    if not u:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "username": u.get("username"), "role": u.get("role")})


# -----------------------------
# Blog debug search (NoSQLi)
# -----------------------------
@app.route("/api/search")
def blog_debug_search():
    lab_domain = _lab_domain()
    if surface_from_host(request.host, lab_domain) != "blog":
        abort(404)
    db = _load_db()

    collection = request.args.get("collection", "posts")
    q_raw = request.args.get("q", "")

    # Intended UX: accept either raw JSON, or a basic substring search.
    q = _json_loads_loose(q_raw) if q_raw else {}

    docs = _collection(db, collection)
    out: List[Dict[str, Any]] = []

    if isinstance(q, dict) and q:
        for d in docs:
            if isinstance(d, dict) and _matches(d, q):
                out.append(d)
    else:
        needle = str(q_raw or "").strip().lower()
        for d in docs:
            if not isinstance(d, dict):
                continue
            if needle and needle not in str(d.get("title", "")).lower():
                continue
            out.append(d)

    return jsonify({"ok": True, "collection": collection, "count": len(out), "results": out})


if __name__ == "__main__":
    port = _safe_int(os.getenv("PORT", "80"), 80)
    app.run(host="0.0.0.0", port=port, debug=False)
