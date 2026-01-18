import os
import json
import time
import base64
import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

import jwt
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

APP_TITLE = "PulsePay Console"
API_BASE = "/api/v1"

DB_PATH = os.getenv("DB_PATH", "/data/pulsepay.db")
JWT_SECRET = os.getenv("JWT_SECRET", "pulsepay-dev-secret")
FLAG = os.getenv("FLAG", "APIVERSE{t0k3n_t0mb_4lg_n0n3}")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=APP_TITLE, version="1.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def pbkdf2_hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return base64.b64encode(salt).decode() + ":" + base64.b64encode(dk).decode()


def pbkdf2_verify(password: str, stored: str) -> bool:
    try:
        salt_b64, dk_b64 = stored.split(":", 1)
        salt = base64.b64decode(salt_b64.encode())
        dk = base64.b64decode(dk_b64.encode())
        test = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return hashlib.compare_digest(test, dk)
    except Exception:
        return False


def b64url_decode(seg: str) -> bytes:
    seg = seg.strip()
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode((seg + pad).encode("utf-8"))


def decode_jwt_vuln(token: str) -> Dict[str, Any]:
    """
    INTENTIONALLY VULNERABLE (training lab):
    - If header alg == "none", accept token WITHOUT verifying a signature.
    - Otherwise verify HS256 with JWT_SECRET.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("bad token")

        header = json.loads(b64url_decode(parts[0]).decode("utf-8"))
        alg = str(header.get("alg", "")).lower()

        if alg == "none":
            payload = json.loads(b64url_decode(parts[1]).decode("utf-8"))
        else:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

        # basic exp check (still leaves alg=none bypass intact)
        exp = payload.get("exp") or payload.get("ext")
        if exp is not None and int(exp) < int(time.time()):
            raise ValueError("expired")

        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def issue_token(username: str, userid: int, role: str) -> str:
    now = int(time.time())
    payload = {
        "username": username,
        "userid": userid,
        "role": role,
        "iat": now,
        "exp": now + 60 * 60,   # 1 hour
        "ext": now + 60 * 60,   # keep the "ext" key too (as requested)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    cookie = request.cookies.get("pp_token")
    if cookie:
        return cookie.strip()

    return None


def require_claims(request: Request) -> Dict[str, Any]:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_jwt_vuln(token)


def require_admin(request: Request) -> Dict[str, Any]:
    claims = require_claims(request)
    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return claims


def init_db() -> None:
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_partners() -> None:
    conn = get_db()
    try:
        existing = conn.execute("SELECT 1 FROM partners LIMIT 1").fetchone()
        if existing:
            return

        partners = [
            ("Kowloon Trade Ltd", "liaison@kowloon-trade.example", "+852 555 0101",
             "Hong Kong reseller. Coordinates cross-border payout corridors for APAC."),
            ("Nordic Settlement AS", "ops@nordic-settlement.example", "+47 555 0202",
             "Norway clearing partner. Handles bank rails reconciliation and dispute batching."),
            ("Saffron Ledger FZE", "finance@saffron-ledger.example", "+971 555 0303",
             f"UAE treasury partner. Maintains liquidity buffers for high-volume merchants. {FLAG}"),
            ("Caspian Bridge OOO", "accounts@caspian-bridge.example", "+7 495 555 0404",
             "Moscow integration vendor. Provides regional KYC review services and risk scoring feeds."),
            ("Marigold Remit SAS", "support@marigold-remit.example", "+33 1 55 55 05 05",
             "Paris PSP partner. Supports SEPA settlement windows and multi-currency conversion."),
        ]

        for name, email, phone, desc in partners:
            conn.execute(
                "INSERT INTO partners (name, email, phone, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, email, phone, desc, utcnow_iso()),
            )
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def on_startup():
    init_db()
    seed_partners()


# ---------------- Pages ----------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    token = request.cookies.get("pp_token")
    if token:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Sign in"})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if not user or not pbkdf2_verify(password, user["password_hash"]):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "title": "Sign in", "error": "Invalid email or password."},
                status_code=401,
            )

        token = issue_token(user["username"], int(user["id"]), "user")
        resp = RedirectResponse(url="/dashboard", status_code=302)
        resp.set_cookie("pp_token", token, httponly=False, samesite="lax")
        return resp
    finally:
        conn.close()


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "title": "Create account"})


@app.post("/signup")
def signup(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
):
    username = username.strip()
    email = email.strip().lower()
    phone = phone.strip()

    if len(password) < 8:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "title": "Create account", "error": "Password must be at least 8 characters."},
            status_code=400,
        )

    conn = get_db()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if exists:
            return templates.TemplateResponse(
                "signup.html",
                {"request": request, "title": "Create account", "error": "Email already exists."},
                status_code=400,
            )

        pw_hash = pbkdf2_hash_password(password)
        conn.execute(
            "INSERT INTO users (username, email, phone, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, email, phone, pw_hash, utcnow_iso()),
        )
        conn.commit()

        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        token = issue_token(username, int(user_id), "user")
        resp = RedirectResponse(url="/dashboard", status_code=302)
        resp.set_cookie("pp_token", token, httponly=False, samesite="lax")
        return resp
    finally:
        conn.close()


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie("pp_token")
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    token = request.cookies.get("pp_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)

    claims = decode_jwt_vuln(token)
    is_admin = (claims.get("role") == "admin")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "username": claims.get("username", "user"),
            "role": claims.get("role", "user"),
            "is_admin": is_admin,
        },
    )


@app.get("/dashboard/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    token = request.cookies.get("pp_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    claims = decode_jwt_vuln(token)

    return templates.TemplateResponse(
        "billing.html",
        {
            "request": request,
            "title": "Billing",
            "username": claims.get("username", "user"),
            "role": claims.get("role", "user"),
            "is_admin": claims.get("role") == "admin",
        },
    )


@app.get("/dashboard/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    token = request.cookies.get("pp_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)
    claims = decode_jwt_vuln(token)

    # pull user fields from DB for display
    conn = get_db()
    try:
        u = conn.execute("SELECT * FROM users WHERE id = ?", (int(claims["userid"]),)).fetchone()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "title": "Account Settings",
            "username": claims.get("username", "user"),
            "role": claims.get("role", "user"),
            "is_admin": claims.get("role") == "admin",
            "user": dict(u) if u else None,
        },
    )


@app.post("/dashboard/settings")
def settings_update(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(""),
):
    claims = require_claims(request)

    username = username.strip()
    email = email.strip().lower()
    phone = phone.strip()

    conn = get_db()
    try:
        # Update user record (NOTE: intentionally does not touch role)
        if password and len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

        if password:
            pw_hash = pbkdf2_hash_password(password)
            conn.execute(
                "UPDATE users SET username=?, email=?, phone=?, password_hash=? WHERE id=?",
                (username, email, phone, pw_hash, int(claims["userid"])),
            )
        else:
            conn.execute(
                "UPDATE users SET username=?, email=?, phone=? WHERE id=?",
                (username, email, phone, int(claims["userid"])),
            )
        conn.commit()
    finally:
        conn.close()

    # Re-issue token with same role claim (still vulnerable if user swaps role in token)
    new_token = issue_token(username, int(claims["userid"]), str(claims.get("role", "user")))
    resp = RedirectResponse(url="/dashboard/settings", status_code=302)
    resp.set_cookie("pp_token", new_token, httponly=False, samesite="lax")
    return resp


@app.get("/dashboard/partners", response_class=HTMLResponse)
def partners_page(request: Request):
    token = request.cookies.get("pp_token")
    if not token:
        return RedirectResponse(url="/login", status_code=302)

    claims = decode_jwt_vuln(token)
    if claims.get("role") != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)

    return templates.TemplateResponse(
        "partners.html",
        {
            "request": request,
            "title": "Foreign Business Partners",
            "username": claims.get("username", "user"),
            "role": claims.get("role", "user"),
            "is_admin": True,
        },
    )


# ---------------- API ----------------

@app.get(f"{API_BASE}/metrics")
def api_metrics(request: Request):
    _ = require_claims(request)

    conn = get_db()
    try:
        active_users = conn.execute("SELECT COUNT(1) FROM users").fetchone()[0]
    finally:
        conn.close()

    # intentionally “marketing-realistic” numbers
    processed_90d_usd = 18_742_930
    countries = {
        "USA": 42,
        "Russia": 9,
        "France": 12,
        "Canada": 14,
        "Japan": 7,
        "Brazil": 16,
    }

    return {
        "active_users": int(active_users),
        "processed_90d_usd": processed_90d_usd,
        "countries": countries,
    }


@app.get(f"{API_BASE}/admin/partnerdata")
def api_partnerdata(request: Request):
    _ = require_admin(request)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT name, email, phone, description FROM partners ORDER BY id ASC"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()
