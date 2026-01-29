import os
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

DB_PATH = os.getenv("DB_PATH", "/data/gitea.db")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "APV_INTERNAL_6d7f9c2b4b")
INTERNAL_API_BASE = os.getenv("INTERNAL_API_BASE", "http://internal-api.ubihard.local")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Gitea Portal", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

def seed() -> None:
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        # bob creds from chat
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("bob", sha256_hex("P@ym3ntP1v0t!2026"), utcnow_iso()),
        )
        conn.commit()
    finally:
        conn.close()

@app.on_event("startup")
def on_startup():
    init_db()
    seed()

def session_get(request: Request) -> Optional[dict]:
    raw = request.cookies.get("gitea_session")
    if not raw:
        return None
    try:
        import json
        return json.loads(raw)
    except Exception:
        return None

def session_set(resp: RedirectResponse, username: str) -> None:
    import json
    resp.set_cookie("gitea_session", json.dumps({"username": username}), httponly=False, samesite="lax")

def session_clear(resp: RedirectResponse) -> None:
    resp.delete_cookie("gitea_session")

def current_user(request: Request) -> Optional[str]:
    s = session_get(request)
    if not s:
        return None
    return s.get("username")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if current_user(request):
        return RedirectResponse("/home", status_code=302)
    return RedirectResponse("/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Sign in"})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip().lower()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and sha256_hex(password) == row["password_hash"]:
            resp = RedirectResponse("/home", status_code=302)
            session_set(resp, username)
            return resp
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "title": "Sign in", "error": "Invalid credentials."},
            status_code=401,
        )
    finally:
        conn.close()

@app.get("/logout")
def logout(request: Request):
    resp = RedirectResponse("/login", status_code=302)
    session_clear(resp)
    return resp

@app.get("/home", response_class=HTMLResponse)
def home_page(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    repos = [
        {"name": "internal-api", "desc": "Ops endpoints for game server status probes", "updated": "2 days ago"}
    ]
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "title": "Repositories", "username": u, "repos": repos},
    )

@app.get("/repo/internal-api", response_class=HTMLResponse)
def repo_page(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    files = [
        {"path": "README.md", "type": "file"},
        {"path": "docs/openapi.yaml", "type": "file"},
        {"path": "src/probe.py", "type": "file"},
    ]
    return templates.TemplateResponse(
        "repo.html",
        {
            "request": request,
            "title": "internal-api",
            "username": u,
            "repo": "internal-api",
            "files": files,
        },
    )

@app.get("/repo/internal-api/commits", response_class=HTMLResponse)
def commits_page(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    commits = [
        {"id": "c9f2b1e", "msg": "Add probe endpoint + basic key auth", "when": "2 days ago"},
        {"id": "a1d0f44", "msg": "Initial scaffold (temp config)", "when": "3 weeks ago"},
    ]
    return templates.TemplateResponse(
        "commits.html",
        {"request": request, "title": "Commits", "username": u, "repo": "internal-api", "commits": commits},
    )

@app.get("/repo/internal-api/commit/{commit_id}", response_class=HTMLResponse)
def commit_view(request: Request, commit_id: str):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    # Older commit leaks the API key
    if commit_id == "a1d0f44":
        diff = f"""
diff --git a/config.py b/config.py
new file mode 100644
index 0000000..1a2b3c4
--- /dev/null
+++ b/config.py
@@
+INTERNAL_API_BASE = "{INTERNAL_API_BASE}"
+# TODO: rotate before production
+INTERNAL_API_KEY = "{INTERNAL_API_KEY}"
"""
    else:
        diff = """
diff --git a/src/probe.py b/src/probe.py
index 11aa22b..33cc44d 100644
--- a/src/probe.py
+++ b/src/probe.py
@@
+added: /api/v1/ops/probe (POST)
+header: X-API-Key
"""

    return templates.TemplateResponse(
        "commit_view.html",
        {
            "request": request,
            "title": f"Commit {commit_id}",
            "username": u,
            "repo": "internal-api",
            "commit_id": commit_id,
            "diff": diff.strip(),
        },
    )
