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

DB_PATH = os.getenv("DB_PATH", "/data/chat.db")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="UbiHard Chat", version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

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
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT NOT NULL,
              author TEXT NOT NULL,
              body TEXT NOT NULL,
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

        # QA creds match main app (so reuse is meaningful)
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            ("qa@ubihard.local", md5_hex("qa2026!"), utcnow_iso()),
        )

        # messages
        msgs = [
            ("#devops", "admin", "Heads up: the SCM portal is back online. Bob has access to the internal API repo.", utcnow_iso()),
            ("#devops", "bob", "Nice. Where is it hosted again?", utcnow_iso()),
            ("#devops", "admin", "Gitea portal: gitea.ubihard.local", utcnow_iso()),
            ("#devops", "admin", "Login for you: bob / P@ym3ntP1v0t!2026", utcnow_iso()),
            ("#devops", "bob", "Got it. Anything I should look for?", utcnow_iso()),
            ("#devops", "admin", "Internal API key is in an older commit (we should rotate it). Repo: internal-api", utcnow_iso()),
            ("#devops", "bob", "💀 okay… I’ll grab it and wire the status probe.", utcnow_iso()),
        ]
        for ch, author, body, ts in msgs:
            conn.execute(
                "INSERT INTO messages (channel, author, body, created_at) VALUES (?, ?, ?, ?)",
                (ch, author, body, ts),
            )

        conn.commit()
    finally:
        conn.close()

@app.on_event("startup")
def on_startup():
    init_db()
    seed()

def session_get(request: Request) -> Optional[dict]:
    raw = request.cookies.get("chat_session")
    if not raw:
        return None
    try:
        import json
        return json.loads(raw)
    except Exception:
        return None

def session_set(resp: RedirectResponse, email: str) -> None:
    import json
    resp.set_cookie("chat_session", json.dumps({"email": email}), httponly=False, samesite="lax")

def session_clear(resp: RedirectResponse) -> None:
    resp.delete_cookie("chat_session")

def current_user(request: Request) -> Optional[str]:
    s = session_get(request)
    if not s:
        return None
    return s.get("email")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if current_user(request):
        return RedirectResponse("/chat", status_code=302)
    return RedirectResponse("/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Sign in"})

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row and md5_hex(password) == row["password_hash"]:
            resp = RedirectResponse("/chat", status_code=302)
            session_set(resp, email)
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

@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request):
    email = current_user(request)
    if not email:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        msgs = conn.execute(
            "SELECT channel, author, body, created_at FROM messages ORDER BY id ASC"
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "title": "UbiHard Chat", "email": email, "messages": msgs},
    )
