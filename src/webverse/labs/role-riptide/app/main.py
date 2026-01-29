import os
import json
import sqlite3
import jwt
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext

APP_TITLE = "LedgerWorks | Internal Projects"
API_BASE = "/api/v1"

DB_PATH = os.getenv("DB_PATH", "/data/apiverse.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret")
FLAG = os.getenv("FLAG", "WEBVERSE{dev_flag}")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

app = FastAPI(title=APP_TITLE, version="1.0.0", docs_url=None, redoc_url=None)

COOKIE_NAME = "apv_token"
TOKEN_TTL_HOURS = 8


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              phone TEXT NOT NULL DEFAULT '',
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'user',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              category TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tax_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              project_id INTEGER NOT NULL,
              client_name TEXT NOT NULL,
              ssn TEXT NOT NULL,
              tax_year INTEGER NOT NULL,
              filing_status TEXT NOT NULL,
              gross_income_cents INTEGER NOT NULL,
              notes TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS pii_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              project_id INTEGER NOT NULL,
              full_name TEXT NOT NULL,
              email TEXT NOT NULL,
              phone TEXT NOT NULL,
              address TEXT NOT NULL,
              dob TEXT NOT NULL,
              notes TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (project_id) REFERENCES projects(id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_data() -> None:
    conn = get_db()
    try:
        has_projects = conn.execute("SELECT 1 FROM projects LIMIT 1").fetchone()
        if has_projects:
            return

        conn.execute(
            "INSERT INTO projects (name, category, created_at) VALUES (?, ?, ?)",
            ("2025 Client Filings - Northshore Portfolio", "tax-records", utcnow_iso()),
        )
        tax_project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO projects (name, category, created_at) VALUES (?, ?, ?)",
            ("Onboarding QA - Client Contact Registry", "pii", utcnow_iso()),
        )
        pii_project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        tax_rows = [
            (tax_project_id, "Evelyn Carter", "193-48-5521", 2025, "Single", 184_220_00, "Schedule C included. Audit risk low."),
            (tax_project_id, "Marcos Nguyen", "551-09-4412", 2025, "Married", 321_550_00, "K-1s received from two entities."),
            (tax_project_id, "Sofia Bennett", "440-18-0294", 2025, "Head of Household", 98_730_00, "Charitable donations require substantiation."),
        ]
        for (pid, cn, ssn, year, status, income, notes) in tax_rows:
            conn.execute(
                """
                INSERT INTO tax_records
                (project_id, client_name, ssn, tax_year, filing_status, gross_income_cents, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pid, cn, ssn, year, status, income, notes, utcnow_iso()),
            )

        pii_rows = [
            (pii_project_id, "Liam O'Reilly", "liam.oreilly@clientmail.example", "+1 (506) 555-0192", "17 Harbourview Rd, Saint John, NB", "1991-02-14", "VIP client; prefers email."),
            (pii_project_id, "Amina Khalid", "amina.khalid@clientmail.example", "+1 (506) 555-0117", "220 King St W, Fredericton, NB", "1987-10-08", "Do not call after 6pm."),
            (pii_project_id, "Noah Tremblay", "noah.tremblay@clientmail.example", "+1 (506) 555-0139", "8 Maplewood Dr, Moncton, NB", "1994-07-27", "Billing contact is spouse."),
        ]
        for (pid, fn, email, phone, addr, dob, notes) in pii_rows:
            conn.execute(
                """
                INSERT INTO pii_records
                (project_id, full_name, email, phone, address, dob, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pid, fn, email, phone, addr, dob, notes, utcnow_iso()),
            )

        conn.commit()
    finally:
        conn.close()


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_user_from_token(request: Request) -> Optional[sqlite3.Row]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()

    if not token:
        return None

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        user_id = int(decoded.get("sub"))
    except Exception:
        return None

    conn = get_db()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def require_user(request: Request) -> sqlite3.Row:
    user = get_user_from_token(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request) -> sqlite3.Row:
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


@app.on_event("startup")
def on_startup():
    init_db()
    seed_data()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_user_from_token(request)
    return RedirectResponse("/dashboard" if user else "/login", status_code=302)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "title": "Create account"})


@app.post("/signup")
def signup(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    name = name.strip()
    email = email.strip().lower()

    if len(password) < 8:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "title": "Create account", "error": "Password must be at least 8 characters."},
            status_code=400,
        )

    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return templates.TemplateResponse(
                "signup.html",
                {"request": request, "title": "Create account", "error": "Email already exists."},
                status_code=400,
            )

        pw_hash = pwd_context.hash(password)
        conn.execute(
            "INSERT INTO users (name, email, phone, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, "", pw_hash, "user", utcnow_iso()),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

        token = create_token(int(user_id))
        resp = RedirectResponse(url="/dashboard", status_code=302)
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
        return resp
    finally:
        conn.close()


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Sign in"})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not pwd_context.verify(password, user["password_hash"]):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "title": "Sign in", "error": "Invalid email or password."},
                status_code=401,
            )

        token = create_token(int(user["id"]))
        resp = RedirectResponse(url="/dashboard", status_code=302)
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
        return resp
    finally:
        conn.close()


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = get_user_from_token(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "user": dict(user),
        },
    )


@app.get("/dashboard/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    user = get_user_from_token(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("profile.html", {"request": request, "title": "Profile", "user": dict(user)})


@app.get("/dashboard/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    user = get_user_from_token(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("billing.html", {"request": request, "title": "Billing", "user": dict(user)})


@app.get("/dashboard/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    user = get_user_from_token(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("settings.html", {"request": request, "title": "Account settings", "user": dict(user)})


@app.get("/dashboard/classified", response_class=HTMLResponse)
def classified_page(request: Request):
    user = get_user_from_token(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse("classified.html", {"request": request, "title": "Classified Projects", "user": dict(user), "api_base": API_BASE})


# ------------------ API ------------------------

@app.get(f"{API_BASE}/me")
def api_me(request: Request):
    user = require_user(request)
    return {"id": user["id"], "name": user["name"], "email": user["email"], "phone": user["phone"], "role": user["role"]}


@app.put(f"{API_BASE}/account")
async def api_update_account(request: Request):
    """
    VULNERABILITY (training): Mass assignment / BOPLA
    The server blindly applies client-provided fields, including 'role'.
    """
    user = require_user(request)
    body = await request.json()  # fastapi will allow await in async; keeping simple
    # NOTE: FastAPI Request.json() is async normally; this sync call works in some cases
    # but to be safe you can change this function to async and use: body = await request.json()
    if isinstance(body, dict) is False:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    allowed_like_fields = ["name", "email", "phone", "password", "role"]
    updates = {k: body.get(k) for k in allowed_like_fields if k in body}

    if "email" in updates and isinstance(updates["email"], str):
        updates["email"] = updates["email"].strip().lower()

    if "password" in updates:
        pw = str(updates["password"] or "")
        if pw:
            updates["password_hash"] = pwd_context.hash(pw)
        updates.pop("password", None)

    set_parts = []
    params = []
    for k, v in updates.items():
        if k == "password_hash":
            set_parts.append("password_hash = ?")
            params.append(v)
        else:
            set_parts.append(f"{k} = ?")
            params.append(v)

    if not set_parts:
        return {"ok": True}

    params.append(user["id"])

    conn = get_db()
    try:
        conn.execute(f"UPDATE users SET {', '.join(set_parts)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()

    return {"ok": True}


@app.get(f"{API_BASE}/admin/records")
def api_admin_records(request: Request):
    require_admin(request)
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT tr.client_name, tr.ssn, tr.tax_year, tr.filing_status, tr.gross_income_cents, tr.notes, p.name AS project
            FROM tax_records tr
            JOIN projects p ON p.id = tr.project_id
            ORDER BY tr.id ASC
            """
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get(f"{API_BASE}/admin/information")
def api_admin_information(request: Request):
    require_admin(request)
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT pr.full_name, pr.email, pr.phone, pr.address, pr.dob, pr.notes, p.name AS project
            FROM pii_records pr
            JOIN projects p ON p.id = pr.project_id
            ORDER BY pr.id ASC
            """
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get(f"{API_BASE}/admin/config")
def api_admin_config(request: Request):
    require_admin(request)
    return {
        "service": "ledgerworks-internal",
        "env": "prod-sim",
        "jwt_secret_hint": "rotated quarterly",
        "feature_flags": {"bulk_import": True, "new_billing": False},
        "flag": FLAG,
    }
