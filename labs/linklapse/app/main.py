from __future__ import annotations

import base64
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
import time
import html
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from flask import Flask, request, make_response, redirect, render_template, jsonify, abort

APP = Flask(__name__, template_folder="templates", static_folder="static")

DB_PATH = os.environ.get("DB_PATH", "/data/linklapse.db")
LAB_DOMAIN = os.environ.get("LAB_DOMAIN", "linklapse.local")
FLAG = os.environ.get("FLAG", "WEBVERSE{dev_flag_change_me}")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "marin.ops@linklapse.local")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "WinterOps!2026")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support.agent@linklapse.local")

COOKIE_NAME = "OPALSESS"
COOKIE_DOMAIN = f".{LAB_DOMAIN}"

IDP_COOKIE = "OIDSESS"
IDP_COOKIE_DOMAIN = f".{LAB_DOMAIN}"

INTERNAL_ADDRS = {"127.0.0.1", "::1"}


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def surface_from_host(host: str) -> str:
    h = (host or "").split(":")[0].lower()
    if h.startswith("chat."):
        return "chat"
    if h.startswith("ops."):
        return "ops"
    if h.startswith("id."):
        return "idp"
    if h.startswith("blog-api."):
        return "blog_api"
    if h.startswith("blog."):
        return "blog"
    if h.startswith("app."):
        return "app"
    return "app"


@dataclass
class Session:
    email: str
    role: str


def get_session() -> Optional[Session]:
    tok = request.cookies.get(COOKIE_NAME)
    if not tok:
        return None
    m = re.match(r"^([^:]+):([^:]+):[a-f0-9]{16,}$", tok)
    if not m:
        return None
    email = m.group(1)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return Session(email=email, role=row["role"])


def require_login() -> Session:
    s = get_session()
    if not s:
        abort(401)
    return s


def require_admin() -> Session:
    s = require_login()
    if s.role != "admin":
        abort(403)
    return s


def set_session_cookie(resp, email: str, role: str) -> None:
    token = f"{email}:{role}:{secrets.token_hex(10)}"
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="Lax",
        secure=False,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def clear_session_cookie(resp) -> None:
    resp.set_cookie(COOKIE_NAME, "", expires=0, domain=COOKIE_DOMAIN, path="/")

def is_internal_request() -> bool:
    """
    Treat only loopback as internal.
    In Docker, browser traffic will show up as a bridge IP (e.g. 172.x),
    while in-container calls to 127.0.0.1 remain loopback.
    """
    ra = (request.remote_addr or "").strip()
    return ra in INTERNAL_ADDRS

def extract_urls(text: str) -> list[str]:
    # Basic URL grabber; good enough for lab chat text
    return re.findall(r"(https?://[^\s]+)", text or "")


# -------------------- IDP (LinkID) --------------------

def idp_get_user() -> Optional[str]:
    return request.cookies.get(IDP_COOKIE)


def idp_set_user(resp, email: str) -> None:
    resp.set_cookie(
        IDP_COOKIE,
        email,
        httponly=True,
        samesite="Lax",
        secure=False,
        domain=IDP_COOKIE_DOMAIN,
        path="/",
    )


def idp_clear_user(resp) -> None:
    resp.set_cookie(IDP_COOKIE, "", expires=0, domain=IDP_COOKIE_DOMAIN, path="/")


def idp_issue_code(linkid_email: str) -> str:
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO idp_users(email,sub) VALUES(?,?)",
        (linkid_email, "linkid|" + secrets.token_hex(8)),
    )
    cur.execute("SELECT sub FROM idp_users WHERE email=?", (linkid_email,))
    sub = cur.fetchone()["sub"]

    code = secrets.token_urlsafe(16)
    exp = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur.execute(
        "INSERT OR REPLACE INTO oauth_codes(code,sub,email,expires_at) VALUES(?,?,?,?)",
        (code, sub, linkid_email, exp),
    )
    conn.commit()
    conn.close()
    return code


def idp_exchange_code(code: str) -> Optional[dict]:
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT code, sub, email, expires_at FROM oauth_codes WHERE code=?", (code,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    if row["expires_at"] < now_iso():
        conn.close()
        return None
    cur.execute("DELETE FROM oauth_codes WHERE code=?", (code,))
    conn.commit()
    conn.close()
    return {"sub": row["sub"], "email": row["email"]}


# -------------------- DB init --------------------

def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS idp_users (
            email TEXT PRIMARY KEY,
            sub TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_codes (
            code TEXT PRIMARY KEY,
            sub TEXT NOT NULL,
            email TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS opalid_links (
            sub TEXT PRIMARY KEY,
            linked_email TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            clicked INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # Blog
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS blog_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute("SELECT 1 FROM users WHERE email=?", (ADMIN_EMAIL,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users(email,password,role) VALUES(?,?,?)", (ADMIN_EMAIL, ADMIN_PASS, "admin"))

    cur.execute("SELECT 1 FROM users WHERE email=?", (SUPPORT_EMAIL,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users(email,password,role) VALUES(?,?,?)", (SUPPORT_EMAIL, secrets.token_hex(12), "support"))

    # Seed blog posts (gibberish)
    cur.execute("SELECT COUNT(*) AS c FROM blog_posts")
    if (cur.fetchone()["c"] or 0) == 0:
        gib = [
            ("v3.8.11 post-mortem fragments", "zlxr qvnt… staccato metrics… nothing to see…"),
            ("ramblings of a reverse proxy", "haprxy? nginx? the truth is in the headers."),
            ("on-call dreams in hex", "3a 3a 3a 0a 6f 70 73 2d 74 72 69 61 67 65"),
            ("winter deployment notes", "rotate tokens, never log secrets, definitely never do LDAP binds in prod."),
            ("misc: coffee, pager, repeat", "pagerduty @ 03:12. yawning. reboot. ship."),
        ]
        for t, b in gib:
            cur.execute("INSERT INTO blog_posts(title,body) VALUES(?,?)", (t, b))

    logs_path = os.path.join(os.path.dirname(DB_PATH), "auth-ops.log")
    if not os.path.exists(logs_path):
        with open(logs_path, "w", encoding="utf-8") as f:
            f.write(f"{now_iso()} INFO web login attempt email=qa.user@linklapse.local result=fail\n")
            f.write(f"{now_iso()} WARN ldap bind failed dn=cn=svc_exports,ou=svc,dc=linklapse,dc=local reason=invalidCredentials\n")
            f.write(f"{now_iso()} ERROR ldap bind failed user=svc_exports password={FLAG} src=10.10.12.44\n")
            f.write(f"{now_iso()} INFO ops export action=customer_export actor={ADMIN_EMAIL}\n")

    conn.commit()
    conn.close()


# -------------------- App routing --------------------

@APP.route("/")
def root():
    surf = surface_from_host(request.host)
    s = get_session()

    if surf == "idp":
        return render_template("idp_home.html", domain=LAB_DOMAIN, idp_user=idp_get_user())

    if surf == "chat":
        if not s:
            return redirect(f"http://app.{LAB_DOMAIN}/auth/login?next=http://chat.{LAB_DOMAIN}/channel/general")
        return redirect("/channel/general")

    if surf == "ops":
        if not s:
            return redirect(f"http://app.{LAB_DOMAIN}/auth/login?next=http://ops.{LAB_DOMAIN}/")
        if s.role != "admin":
            return render_template("ops_denied.html", domain=LAB_DOMAIN, session=s)
        return render_template("ops_home.html", domain=LAB_DOMAIN, session=s)

    if surf == "blog":
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT id,title FROM blog_posts ORDER BY id ASC")
        posts = cur.fetchall()
        conn.close()
        return render_template("blog_home.html", domain=LAB_DOMAIN, posts=posts)

    return render_template("app_home.html", domain=LAB_DOMAIN, session=s)


# -------------------- Blog pages --------------------

@APP.route("/post/<int:pid>")
def blog_post(pid: int):
    if surface_from_host(request.host) != "blog":
        abort(404)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id,title,body FROM blog_posts WHERE id=?", (pid,))
    post = cur.fetchone()
    if not post:
        conn.close()
        abort(404)
    cur.execute("SELECT author, body, created_at FROM blog_comments WHERE post_id=? ORDER BY id ASC", (pid,))
    comments = cur.fetchall()
    conn.close()
    return render_template("blog_post.html", domain=LAB_DOMAIN, post=post, comments=comments)


# -------------------- Blog API (posting) --------------------

@APP.route("/api/v1/comments", methods=["GET", "POST"])
def blog_api_comments():
    if surface_from_host(request.host) != "blog_api":
        abort(404)

    if request.method == "GET":
        post_id = int(request.args.get("post_id") or "0")
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT author, body, created_at FROM blog_comments WHERE post_id=? ORDER BY id ASC", (post_id,))
        rows = cur.fetchall()
        conn.close()
        return jsonify({"post_id": post_id, "count": len(rows), "comments": [dict(r) for r in rows]})

    # POST — allow anonymous; used by blog UI + used by bot (intended exfil sink)
    try:
        j = request.get_json(force=True, silent=True) or {}
    except Exception:
        j = {}

    post_id = int(j.get("post_id") or 0)
    author = (j.get("author") or "anon").strip()[:60]
    body = (j.get("body") or "").strip()
    if not post_id or not body:
        return jsonify({"ok": False, "msg": "post_id and body required"}), 400

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM blog_posts WHERE id=?", (post_id,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"ok": False, "msg": "unknown post"}), 404

    cur.execute(
        "INSERT INTO blog_comments(post_id,author,body,created_at) VALUES(?,?,?,?)",
        (post_id, author, body, now_iso()),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# -------------------- App auth --------------------

@APP.route("/auth/login", methods=["GET", "POST"])
def auth_login():
    if surface_from_host(request.host) != "app":
        return redirect(f"http://app.{LAB_DOMAIN}/auth/login")

    if request.method == "GET":
        return render_template("login.html", domain=LAB_DOMAIN, error=None)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT email,password,role FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()

    if not row or row["password"] != password:
        return render_template("login.html", domain=LAB_DOMAIN, error="Invalid credentials.")

    resp = make_response(redirect(request.args.get("next") or f"http://app.{LAB_DOMAIN}/"))
    set_session_cookie(resp, row["email"], row["role"])
    return resp


@APP.route("/auth/logout")
def auth_logout():
    if surface_from_host(request.host) != "app":
        return redirect(f"http://app.{LAB_DOMAIN}/auth/logout")
    resp = make_response(redirect(f"http://app.{LAB_DOMAIN}/"))
    clear_session_cookie(resp)
    return resp

@APP.route("/auth/trouble", methods=["GET"])
def auth_trouble():
    """
    Public "Trouble signing in?" page.
    Intentionally does NOT require an app session.

    This is the discoverability breadcrumb for the linking flow:
    - It explains "LinkID must be linked to a local account"
    - Provides a UI to initiate the link mode
    """
    if surface_from_host(request.host) != "app":
        return redirect(f"http://app.{LAB_DOMAIN}/auth/trouble")

    # If user is already logged in, we can still show it; doesn't matter.
    return render_template(
        "trouble_signin.html",
        domain=LAB_DOMAIN,
        prefill="",
        error=None,
    )


@APP.route("/auth/opalid/link", methods=["POST"])
def auth_opalid_link_post():
    """
    Public form POST target that redirects into the existing OAuth start endpoint
    using mode=link + target_email.
    """
    if surface_from_host(request.host) != "app":
        return redirect(f"http://app.{LAB_DOMAIN}/auth/trouble")

    target_email = (request.form.get("target_email") or "").strip().lower()
    if not target_email or "@" not in target_email:
        return render_template(
            "trouble_signin.html",
            domain=LAB_DOMAIN,
            prefill=html.escape(target_email),
            error="Enter a valid email to link.",
        )

    # Redirect into the existing flow (this preserves your intended vuln).
    return redirect(f"/auth/opalid/start?{urlencode({'mode': 'link', 'target_email': target_email})}")


# -------------------- OAuth Start / Callback (VULN HERE) --------------------

@APP.route("/auth/opalid/start")
def opalid_start():
    if surface_from_host(request.host) != "app":
        return redirect(f"http://app.{LAB_DOMAIN}/auth/opalid/start")

    mode = (request.args.get("mode") or "login").lower()
    state = secrets.token_urlsafe(10)

    # IMPORTANT: IdP only returns `code` + `state` to redirect_uri.
    # So for link-mode, we must embed mode/target_email into redirect_uri itself.
    redirect_uri = f"http://app.{LAB_DOMAIN}/auth/opalid/callback"
    if mode == "link":
        redirect_uri = redirect_uri + "?" + urlencode({
            "mode": "link",
            "target_email": request.args.get("target_email", ""),
        })

    params = {
        "client_id": "linklapse-web",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "approve": "1",
    }

    url = f"http://id.{LAB_DOMAIN}/oauth/authorize?{urlencode(params)}"
    return redirect(url)


@APP.route("/auth/opalid/callback")
def opalid_callback():
    if surface_from_host(request.host) != "app":
        return redirect(f"http://app.{LAB_DOMAIN}/auth/opalid/callback?{request.query_string.decode()}")

    code = request.args.get("code") or ""
    mode = (request.args.get("mode") or "login").lower()
    target_email = (request.args.get("target_email") or "").strip().lower()

    info = idp_exchange_code(code)
    if not info:
        return render_template("oauth_result.html", domain=LAB_DOMAIN, ok=False, msg="Invalid or expired code.")

    sub = info["sub"]

    # VULN: anyone can link any sub -> any local account (no auth check)
    if mode == "link":
        if not target_email:
            return render_template("oauth_result.html", domain=LAB_DOMAIN, ok=False, msg="Missing target_email.")
        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE email=?", (target_email,))
        if not cur.fetchone():
            conn.close()
            return render_template("oauth_result.html", domain=LAB_DOMAIN, ok=False, msg="Unknown local user.")
        cur.execute("INSERT OR REPLACE INTO opalid_links(sub,linked_email) VALUES(?,?)", (sub, target_email))
        conn.commit()
        conn.close()

        return render_template(
            "oauth_result.html",
            domain=LAB_DOMAIN,
            ok=True,
            msg=f"LinkID linked to {target_email}. You can now 'Login with LinkID'.",
        )

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT linked_email FROM opalid_links WHERE sub=?", (sub,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return render_template("oauth_result.html", domain=LAB_DOMAIN, ok=False, msg="No local account linked for this LinkID.")
    linked_email = row["linked_email"]
    cur.execute("SELECT role FROM users WHERE email=?", (linked_email,))
    u = cur.fetchone()
    conn.close()

    resp = make_response(redirect(f"http://app.{LAB_DOMAIN}/"))
    set_session_cookie(resp, linked_email, u["role"])
    return resp


# -------------------- Client bundle leak (blog discovery + logs path leak) --------------------

@APP.route("/static/app.bundle.js")
def bundle_js():
    js = f"""// LinkLapse client bundle (trimmed)
window.__LINKLAPSE__ = {{
  apiBase: "http://app.{LAB_DOMAIN}",
  logsV3Path: "/api/v3/logs",
  blogApiBase: "http://blog-api.{LAB_DOMAIN}", // legacy blog comment service
  // Used by the support widget to prefill escalation routing.
  adminEmail: "{ADMIN_EMAIL}",
  build: "2026.01.29"
}};
"""
    resp = make_response(js)
    resp.headers["Content-Type"] = "application/javascript"
    return resp


# -------------------- Chat --------------------

@APP.route("/channel/<name>")
def chat_channel(name: str):
    if surface_from_host(request.host) != "chat":
        return redirect(f"http://chat.{LAB_DOMAIN}/channel/{name}")

    s = get_session()
    if not s:
        return redirect(f"http://app.{LAB_DOMAIN}/auth/login?next=http://chat.{LAB_DOMAIN}/channel/{name}")

    channels = ["general", "support", "ops-triage"]

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id,author,body,created_at FROM chat_messages WHERE channel=? ORDER BY id DESC LIMIT 60", (name,))
    rows = list(reversed(cur.fetchall()))
    conn.close()

    return render_template("chat_channel.html", domain=LAB_DOMAIN, session=s, channel=name, channels=channels, messages=rows)


@APP.route("/chat/send", methods=["POST"])
def chat_send():
    if surface_from_host(request.host) != "chat":
        abort(404)
    s = require_login()

    channel = (request.form.get("channel") or "general").strip()
    body = (request.form.get("body") or "").strip()
    if not body:
        return redirect(f"/channel/{channel}")

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_messages(channel,author,body,created_at,clicked) VALUES(?,?,?,?,0)",
        (channel, s.email, body, now_iso()),
    )
    conn.commit()
    conn.close()
    return redirect(f"/channel/{channel}")


@APP.route("/leave")
def chat_leave():
    if surface_from_host(request.host) != "chat":
        abort(404)
    require_login()
    nxt = request.args.get("next", "")
    return render_template("chat_leave.html", domain=LAB_DOMAIN, nxt=nxt)


# -------------------- Logs API (CORS misconfig) --------------------

@APP.route("/api/v3/logs")
def api_logs():
    # Hard internal-only gate (even admins from outside shouldn't see it)
    if not is_internal_request():
        abort(404)

    s = get_session()
    if not s or s.role != "admin":
        abort(401)

    q = (request.args.get("q") or "").lower()
    logs_path = os.path.join(os.path.dirname(DB_PATH), "auth-ops.log")
    with open(logs_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if q:
        lines = [ln for ln in lines if q in ln.lower()]

    resp = jsonify({"count": len(lines), "lines": lines})

    # You can keep or remove these. Keeping them doesn't matter now since
    # endpoint is not reachable externally.
    origin = request.headers.get("Origin") or "*"
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Vary"] = "Origin"
    return resp


# -------------------- IDP routes --------------------

@APP.route("/oauth/login", methods=["GET", "POST"])
def idp_login():
    if surface_from_host(request.host) != "idp":
        return redirect(f"http://id.{LAB_DOMAIN}/oauth/login")

    if request.method == "GET":
        nxt = request.args.get("next", "")
        return render_template("idp_login.html", domain=LAB_DOMAIN, next_url=nxt, error=None)

    email = (request.form.get("email") or "").strip().lower()
    nxt = request.form.get("next") or f"http://id.{LAB_DOMAIN}/"
    if not email or "@" not in email:
        return render_template("idp_login.html", domain=LAB_DOMAIN, next_url=nxt, error="Enter a valid email.")
    resp = make_response(redirect(nxt))
    idp_set_user(resp, email)
    return resp


@APP.route("/oauth/logout")
def idp_logout():
    if surface_from_host(request.host) != "idp":
        return redirect(f"http://id.{LAB_DOMAIN}/oauth/logout")
    resp = make_response(redirect(f"http://id.{LAB_DOMAIN}/"))
    idp_clear_user(resp)
    return resp


@APP.route("/oauth/authorize")
def idp_authorize():
    if surface_from_host(request.host) != "idp":
        return redirect(f"http://id.{LAB_DOMAIN}/oauth/authorize?{request.query_string.decode()}")

    user = idp_get_user()
    if not user:
        nxt = f"http://id.{LAB_DOMAIN}/oauth/authorize?{request.query_string.decode()}"
        return redirect(f"http://id.{LAB_DOMAIN}/oauth/login?{urlencode({'next': nxt})}")

    redirect_uri = request.args.get("redirect_uri") or ""
    state = request.args.get("state") or ""
    approve = request.args.get("approve") or ""

    if approve != "1":
        return render_template("idp_authorize.html", domain=LAB_DOMAIN, user=user, qs=request.query_string.decode())

    code = idp_issue_code(user)
    sep = "&" if "?" in redirect_uri else "?"
    return redirect(f"{redirect_uri}{sep}{urlencode({'code': code, 'state': state})}")


# -------------------- Admin triage bot (base64 exec -> posts exfil as blog comment) --------------------

def _admin_triage_bot() -> None:
    time.sleep(1.5)
    sess = requests.Session()
    base = "http://127.0.0.1"  # loopback so /api/v3/logs passes internal gate
    app_base = f"http://app.{LAB_DOMAIN}"
    chat_base = f"http://chat.{LAB_DOMAIN}"
    blog_api_base = f"http://blog-api.{LAB_DOMAIN}"

    try:
        sess.post(
            app_base + "/auth/login",
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
            timeout=3,
            allow_redirects=False,
        )
    except Exception:
        return

    # Extract the admin session token from the cookie jar.
    # We will manually attach it to loopback requests (127.0.0.1) because
    # requests will not send a .linklapse.local cookie to 127.0.0.1 automatically.
    token = None
    try:
        for c in sess.cookies:
            if c.name == COOKIE_NAME:
                token = c.value
                break
    except Exception:
        token = None
    if not token:
        return
    cookie_hdr = f"{COOKIE_NAME}={token}"

    while True:
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, body FROM chat_messages WHERE channel=? AND clicked=0 ORDER BY id ASC LIMIT 1",
                ("ops-triage",),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                time.sleep(2.0)
                continue

            msg_id = row["id"]
            body = row["body"]

            urls = extract_urls(body)
            if not urls:
                cur.execute("UPDATE chat_messages SET clicked=1 WHERE id=?", (msg_id,))
                conn.commit()
                conn.close()
                time.sleep(1.0)
                continue

            executed = False
            for url in urls:
                try:
                    u = urlparse(url)
                    host = (u.netloc or "").split("@")[-1]  # drop possible userinfo
                    host = host.split(":")[0]

                    # Route back through loopback, but preserve Host so the app's
                    # "surface router" behaves like a real multi-subdomain setup.
                    internal_url = base + (u.path or "/")
                    if u.query:
                        internal_url += "?" + u.query

                    if not host.endswith(LAB_DOMAIN):
                        # External/unknown hosts: still "click" them, but don't
                        # attempt internal exfil behavior.
                        r = sess.get(url, timeout=4, allow_redirects=True)
                        page_html = r.text or ""
                    else:
                        r = sess.get(
                            internal_url,
                            headers={"Host": host, "Cookie": cookie_hdr},
                            timeout=4,
                            allow_redirects=True,
                        )
                        page_html = r.text or ""

                    # Execute the exfil behavior at most once, even if multiple links
                    # are present. Still keep clicking remaining links.
                    if not executed:
                        mexec = re.search(
                            r"exec\s*\(\s*base64decode\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\)",
                            page_html,
                            flags=re.I,
                        )
                        if mexec:
                            b64 = mexec.group(1)
                            try:
                                decoded_js = base64.b64decode(b64.encode()).decode("utf-8", "ignore")
                            except Exception:
                                decoded_js = ""

                            post_id = 1
                            mpid = re.search(r"post_id\s*:\s*(\d+)", decoded_js)
                            if mpid:
                                post_id = int(mpid.group(1))

                            # Pull logs path from leaked client bundle
                            bundle = sess.get(
                                base + "/static/app.bundle.js",
                                headers={"Host": f"app.{LAB_DOMAIN}", "Cookie": cookie_hdr},
                                timeout=4,
                                allow_redirects=True,
                            ).text
                            m2 = re.search(r'logsV3Path:\s*"([^"]+)"', bundle)
                            path = m2.group(1) if m2 else "/api/v3/logs"

                            logs = sess.get(
                                base + path + "?q=ldap",
                                headers={"Host": f"app.{LAB_DOMAIN}", "Cookie": cookie_hdr},
                                timeout=4,
                                allow_redirects=True,
                            )
                            payload = logs.text if hasattr(logs, "text") else ""

                            # Post exfil to blog-api as a comment
                            try:
                                sess.post(
                                    base + "/api/v1/comments",
                                    headers={"Host": f"blog-api.{LAB_DOMAIN}"},
                                    json={"post_id": post_id, "author": "ops-triage-bot", "body": payload},
                                    timeout=4,
                                )
                            except Exception:
                                pass

                            executed = True

                except Exception:
                    # Keep going; we want to "click" everything in the message.
                    pass

            cur.execute("UPDATE chat_messages SET clicked=1 WHERE id=?", (msg_id,))
            conn.commit()
            conn.close()

        except Exception:
            try:
                conn.close()
            except Exception:
                pass

        time.sleep(2.0)


def main() -> None:
    init_db()
    t = threading.Thread(target=_admin_triage_bot, daemon=True)
    t.start()
    APP.run(host="0.0.0.0", port=80, debug=False)


if __name__ == "__main__":
    main()
