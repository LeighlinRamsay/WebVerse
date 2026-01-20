import os
import re
import sqlite3
import time
from collections import defaultdict, deque

from flask import Flask, request, render_template, redirect, session
from jinja2.sandbox import SandboxedEnvironment

app = Flask(__name__)
app.secret_key = "reports-portal-secret"

COMPANY_NAME = "AsterCheck Security"
DB_PATH = "/tmp/reports_portal.db"

# ---- Jinja "hardened sandbox" for the report generator ----
SANDBOX = SandboxedEnvironment(autoescape=True)

# Only allow a single primitive: {{ENV}} (exact token)
ENV_TEMPLATE_RE = re.compile(r"^\s*\{\{\s*ENV\s*\}\}\s*$")

# ---- Login rate limiting ----
# >3 POST /login per 1 second -> block IP for 5 seconds
LOGIN_RATE_WINDOW_SEC = 1.0
LOGIN_RATE_MAX = 3
LOGIN_BLOCK_SECONDS = 5.0

_login_hits = defaultdict(deque)  # ip -> deque[timestamps]
_login_blocked_until = {}         # ip -> unix_epoch_until

# ---- Basic SQLi blacklist (intentionally weak) ----
UNION_RE = re.compile(r"\bUNION\b",)

BLACKLIST = ("UNION", "SELECT", "NULL", "OR", "AND", "IN", "WHERE", "-", "CHAR", "HEX")


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"


def _ban_ip(ip: str, seconds: float = LOGIN_BLOCK_SECONDS) -> None:
    _login_blocked_until[ip] = max(_login_blocked_until.get(ip, 0), time.time() + seconds)


def _is_rate_limited_login(ip: str) -> bool:
    now = time.time()

    # Currently blocked?
    until = _login_blocked_until.get(ip, 0)
    if now < until:
        return True

    q = _login_hits[ip]
    cutoff = now - LOGIN_RATE_WINDOW_SEC
    while q and q[0] < cutoff:
        q.popleft()

    # If this request would exceed max, block and deny
    if len(q) >= LOGIN_RATE_MAX:
        _ban_ip(ip, LOGIN_BLOCK_SECONDS)
        return True

    q.append(now)
    return False


def init_db():
    if os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)")
    cur.execute("INSERT INTO users(username,password,role) VALUES('opsadmin','WinterOps','admin')")
    cur.execute("INSERT INTO users(username,password,role) VALUES('auditor','AuditMeverysoon','read')")
    conn.commit()
    conn.close()


def render_created_by(created_by: str) -> str:
    if not isinstance(created_by, str):
        return ""
    if "{{" not in created_by:
        return created_by
    if not ENV_TEMPLATE_RE.match(created_by):
        return "[blocked-by-template-filter]"
    t = SANDBOX.from_string(created_by)
    return t.render(ENV=dict(os.environ))


@app.get("/")
def home():
    if session.get("authed"):
        return redirect("/dashboard")
    return redirect("/login")


@app.get("/login")
def login_page():
    return render_template("login.html", company_name=COMPANY_NAME)


@app.post("/login")
def do_login():
    init_db()

    ip = _client_ip()
    if _is_rate_limited_login(ip):
        return render_template(
            "login.html",
            company_name=COMPANY_NAME,
            error="Too many attempts. Your IP is temporarily blocked."
        ), 429

    u = request.form.get("username", "")
    p = request.form.get("password", "")

    # Basic blacklist: block UNION (case-insensitive) + ban for 5s when triggered
    #if UNION_RE.search(u) or UNION_RE.search(p):
    #if u in BLACKLIST or p in BLACKLIST:
    for b in BLACKLIST:
        if b in u or b in p:
            _ban_ip(ip, LOGIN_BLOCK_SECONDS)
            return render_template(
                "login.html",
                company_name=COMPANY_NAME,
                error="Blocked input. Your IP is temporarily blocked."
            ), 403

    # INTENTIONALLY VULNERABLE SQLi (for lab):
    q = f"SELECT id,username,role FROM users WHERE username='{u}' AND password='{p}'"

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        row = cur.execute(q).fetchone()
    except Exception:
        row = None
    conn.close()

    if row:
        session["authed"] = True
        session["user"] = row[1]
        session["role"] = row[2]
        return redirect("/dashboard")

    return render_template("login.html", company_name=COMPANY_NAME, error="Invalid credentials"), 401


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.get("/dashboard")
def dashboard():
    if not session.get("authed"):
        return redirect("/login")
    return render_template(
        "dashboard.html",
        company_name=COMPANY_NAME,
        user=session.get("user"),
        role=session.get("role"),
        version=os.environ.get("VERSION", "2.4.8"),
    )


@app.get("/generator")
def generator():
    if not session.get("authed"):
        return redirect("/login")
    return render_template("generator.html", company_name=COMPANY_NAME)


@app.post("/generator")
def generate():
    if not session.get("authed"):
        return redirect("/login")

    created_by = request.form.get("created_by", "")
    for_network = request.form.get("for_network", "")
    date_of_creation = request.form.get("date_of_creation", "")
    internal_use = request.form.get("internal_use", "")
    company = request.form.get("company", "")
    date_of_last_report = request.form.get("date_of_last_report", "")

    created_by_rendered = render_created_by(created_by)

    return render_template(
        "report.html",
        company_name=COMPANY_NAME,
        created_by=created_by_rendered,
        for_network=for_network,
        date_of_creation=date_of_creation,
        internal_use=internal_use,
        company=company,
        date_of_last_report=date_of_last_report,
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)
