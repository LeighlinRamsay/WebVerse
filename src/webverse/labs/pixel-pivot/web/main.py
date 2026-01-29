import os
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

APP_TITLE = "UbiHard Studio Portal"
API_BASE = "/api/v1"

DB_PATH = os.getenv("DB_PATH", "/data/web.db")
APP_DOMAIN = os.getenv("APP_DOMAIN", "ubihard.local")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=APP_TITLE, version="1.0.0", docs_url=None, redoc_url=None)

# ------------------ utils ------------------

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def pbkdf2_sha256_hex(password: str, salt_hex: str, iterations: int = 200_000) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex()

def new_salt_hex(n: int = 16) -> str:
    return secrets.token_hex(n)

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
              role TEXT NOT NULL,
              password TEXT NOT NULL,
              hash_alg TEXT NOT NULL,
              salt TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              studio TEXT NOT NULL,
              release_year INTEGER NOT NULL,
              author_email TEXT NOT NULL,
              image_path TEXT NOT NULL,
              platforms_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reset_tokens (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL,
              otp TEXT NOT NULL,
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
        exists = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if exists:
            return

        # QA user (weak MD5 so it is crackable when dumped)
        qa_email = "qa@ubihard.local"
        qa_pw = "qa2026!"
        conn.execute(
            "INSERT INTO users (email, role, password, hash_alg, salt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (qa_email, "qa", md5_hex(qa_pw), "md5", "", utcnow_iso()),
        )

        # Marlin (strong PBKDF2, not realistically crackable from dump)
        marlin_email = "marlin@ubihard.local"
        marlin_pw = "M4rl1n!G4m3D3v_2026#R@nd0m"
        marlin_salt = new_salt_hex(16)
        marlin_hash = pbkdf2_sha256_hex(marlin_pw, marlin_salt, 250_000)
        conn.execute(
            "INSERT INTO users (email, role, password, hash_alg, salt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (marlin_email, "lead", marlin_hash, "pbkdf2_sha256", marlin_salt, utcnow_iso()),
        )

        games = [
            ("Borderlands", "Gearbox", 2009, "support@gearbox.example", "/static/thumbs/borderlands.svg", ["PC", "PS5", "Xbox"]),
            ("Assassin's Creed", "Ubisoft", 2007, "marlin@ubihard.local", "/static/thumbs/assassins.svg", ["PC", "PS5", "Xbox"]),
            ("Fortnite", "Epic Games", 2017, "security@epic.example", "/static/thumbs/fortnite.svg", ["PC", "Switch", "PS5", "Xbox"]),
            ("GTA", "Rockstar", 2013, "press@rockstar.example", "/static/thumbs/gta.svg", ["PC", "PS5", "Xbox"]),
            ("Stardew Valley", "ConcernedApe", 2016, "hello@concernedape.example", "/static/thumbs/stardew.svg", ["PC", "Switch"]),
            ("Portal", "Valve", 2007, "devrel@valvesoftware.example", "/static/thumbs/portal.svg", ["PC"]),
        ]
        for title, studio, year, author_email, img, platforms in games:
            conn.execute(
                "INSERT INTO games (title, studio, release_year, author_email, image_path, platforms_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (title, studio, year, author_email, img, json.dumps(platforms), utcnow_iso()),
            )

        conn.commit()
    finally:
        conn.close()

def session_get(request: Request) -> Optional[dict]:
    return request.cookies.get("apv_session")

def session_set(resp: RedirectResponse, user_id: int, role: str, email: str) -> None:
    # intentionally simple / lab-ish session cookie
    raw = json.dumps({"user_id": user_id, "role": role, "email": email})
    resp.set_cookie("apv_session", raw, httponly=False, samesite="lax")

def session_clear(resp: RedirectResponse) -> None:
    resp.delete_cookie("apv_session")

def current_user(request: Request) -> Optional[sqlite3.Row]:
    s = session_get(request)
    if not s:
        return None
    try:
        data = json.loads(s)
        uid = int(data.get("user_id"))
    except Exception:
        return None

    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    finally:
        conn.close()

def require_user(request: Request) -> sqlite3.Row:
    u = current_user(request)
    if not u:
        raise Exception("auth")
    return u

def verify_password(password: str, user: sqlite3.Row) -> bool:
    alg = user["hash_alg"]
    if alg == "md5":
        return md5_hex(password) == user["password"]
    if alg == "pbkdf2_sha256":
        return pbkdf2_sha256_hex(password, user["salt"], 250_000) == user["password"]
    return False

def set_password(conn: sqlite3.Connection, email: str, new_password: str) -> None:
    salt = new_salt_hex(16)
    ph = pbkdf2_sha256_hex(new_password, salt, 250_000)
    conn.execute(
        "UPDATE users SET password=?, hash_alg=?, salt=? WHERE email=?",
        (ph, "pbkdf2_sha256", salt, email),
    )

# ------------------ startup ------------------

@app.on_event("startup")
def on_startup():
    init_db()
    seed()

# ------------------ pages ------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    u = current_user(request)
    if u:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Sign in"})

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()

    conn = get_db()
    try:
        # Primary (normal) auth
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and verify_password(password, user):
            resp = RedirectResponse("/dashboard", status_code=302)
            session_set(resp, user["id"], user["role"], user["email"])
            return resp

        # VULNERABILITY (training): legacy auth path is injectable (boolean/UNION)
        # NOTE: this is intentionally bad for lab purposes.
        sql = f"SELECT id, email, role FROM users WHERE email = '{email}' AND password = '{password}' LIMIT 1"
        row = conn.execute(sql).fetchone()
        if row:
            resp = RedirectResponse("/dashboard", status_code=302)
            session_set(resp, row["id"], row["role"], row["email"])
            return resp

        return templates.TemplateResponse(
            "login.html",
            {"request": request, "title": "Sign in", "error": "Invalid email or password."},
            status_code=401,
        )
    finally:
        conn.close()

@app.get("/logout")
def logout(request: Request):
    resp = RedirectResponse("/login", status_code=302)
    session_clear(resp)
    return resp

@app.get("/reset", response_class=HTMLResponse)
def reset_request_page(request: Request):
    return templates.TemplateResponse("reset_request.html", {"request": request, "title": "Reset password"})

@app.post("/reset/request")
def reset_request(request: Request, email: str = Form(...)):
    email = email.strip().lower()

    otp = str(secrets.randbelow(10_000)).zfill(4)  # 0000-9999
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO reset_tokens (email, otp, created_at) VALUES (?, ?, ?)",
            (email, otp, utcnow_iso()),
        )
        conn.commit()
    finally:
        conn.close()

    # Always same response (realistic), but NO rate limits / lockouts.
    return templates.TemplateResponse(
        "reset_request.html",
        {"request": request, "title": "Reset password", "ok": "If the account exists, a code was sent."},
    )

@app.get("/reset/confirm", response_class=HTMLResponse)
def reset_confirm_page(request: Request, email: str = ""):
    return templates.TemplateResponse(
        "reset_confirm.html",
        {"request": request, "title": "Confirm reset", "email_prefill": email},
    )

@app.post("/reset/confirm")
def reset_confirm(request: Request, email: str = Form(...), otp: str = Form(...), new_password: str = Form(...)):
    email = email.strip().lower()
    otp = otp.strip()

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT otp, created_at FROM reset_tokens WHERE email = ? ORDER BY id DESC LIMIT 1",
            (email,),
        ).fetchone()

        if not row:
            return templates.TemplateResponse(
                "reset_confirm.html",
                {"request": request, "title": "Confirm reset", "email_prefill": email, "error": "Invalid code."},
                status_code=400,
            )

        created = datetime.fromisoformat(row["created_at"])
        if datetime.now(timezone.utc) - created > timedelta(minutes=20):
            return templates.TemplateResponse(
                "reset_confirm.html",
                {"request": request, "title": "Confirm reset", "email_prefill": email, "error": "Code expired."},
                status_code=400,
            )

        # VULNERABILITY (training): unlimited attempts, no throttling, no lockout.
        if otp != row["otp"]:
            return templates.TemplateResponse(
                "reset_confirm.html",
                {"request": request, "title": "Confirm reset", "email_prefill": email, "error": "Invalid code."},
                status_code=400,
            )

        set_password(conn, email, new_password)
        conn.commit()

        return RedirectResponse("/login", status_code=302)
    finally:
        conn.close()

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "user_email": u["email"],
            "email": u["email"],
            "role": u["role"],
        },
    )

@app.get("/dashboard/games", response_class=HTMLResponse)
def games_page(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "games.html",
        {"request": request, "title": "Games", "user_email": u["email"], "email": u["email"], "role": u["role"]},
    )

@app.get("/dashboard/devstatus", response_class=HTMLResponse)
def devstatus_page(request: Request):
    u = current_user(request)
    if not u:
        return RedirectResponse("/login", status_code=302)
    if u["role"] not in ("lead", "admin"):
        return RedirectResponse("/dashboard", status_code=302)

    return templates.TemplateResponse(
        "devstatus.html",
        {"request": request, "title": "Development Status", "user_email": u["email"], "email": u["email"], "role": u["role"]},
    )

# ------------------ API ------------------

@app.get(f"{API_BASE}/me")
def api_me(request: Request):
    u = current_user(request)
    if not u:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"email": u["email"], "role": u["role"]}

@app.get(f"{API_BASE}/games")
def api_games(request: Request, q: str = ""):
    u = current_user(request)
    if not u:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    # VULNERABILITY (training): SQL injection in LIKE clause
    # Intended: UNION-based dumping (users table, etc.)
    sql = f"""
        SELECT id, title, studio, release_year, author_email, image_path, platforms_json
        FROM games
        WHERE title LIKE '%{q}%'
        ORDER BY release_year DESC
        LIMIT 50
    """

    conn = get_db()
    try:
        rows = conn.execute(sql).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "studio": r["studio"],
                    "release_year": r["release_year"],
                    "author_email": r["author_email"],  # "leaks" in API response
                    "image": r["image_path"],
                    "platforms": json.loads(r["platforms_json"] or "[]"),
                }
            )
        return {"items": items}
    finally:
        conn.close()

@app.get(f"{API_BASE}/integrations/status")
def api_integrations_status(request: Request):
    u = current_user(request)
    if not u:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return {
        "items": [
            {
                "name": "Internal Chat",
                "status": "Integrated",
                "severity": "ok",
                "endpoint": f"http://chat.{APP_DOMAIN}",
            },
            {
                "name": "Gitea SCM",
                "status": "Offline",
                "severity": "down",
                "endpoint": "",
            },
            {
                "name": "Internal API",
                "status": "Offline",
                "severity": "down",
                "endpoint": "",
            },
        ]
    }
