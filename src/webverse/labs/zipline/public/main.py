import os
import json
import sqlite3
import zipfile
from io import BytesIO
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path

APP_TITLE = "Zipline"
API_BASE = "/api/v1"

DB_PATH = os.getenv("DB_PATH", "/data/public.db")
JWT_SECRET = os.getenv("PUBLIC_JWT_SECRET", "dev-secret")
LAB_DOMAIN = os.getenv("LAB_DOMAIN", "zipline.local")
INTERNAL_SUBDOMAIN = os.getenv("INTERNAL_SUBDOMAIN", "internal-api.zipline.local")
INTERNAL_LOGIN_URL = os.getenv("INTERNAL_LOGIN_URL", f"http://{INTERNAL_SUBDOMAIN}/api/v2/user/login")
INTERNAL_HINT_USER = os.getenv("INTERNAL_HINT_USER", "svc-exporter")
INTERNAL_HINT_PASS = os.getenv("INTERNAL_HINT_PASS", "Spring2026!RotateMe")

SEED_USER_EXPORT_ID = int(os.getenv("SEED_USER_EXPORT_ID", "3"))
SEED_FLAG_EXPORT_ID = int(os.getenv("SEED_FLAG_EXPORT_ID", "564"))

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=APP_TITLE, version="1.0.0", docs_url=None, redoc_url=None)


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
              username TEXT NOT NULL UNIQUE,
              password_hash BLOB NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              public_id INTEGER NOT NULL UNIQUE,
              owner_user_id INTEGER NOT NULL,
              title TEXT NOT NULL,
              created_at TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              debug_json TEXT,
              FOREIGN KEY(owner_user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_exports_owner ON exports(owner_user_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_data() -> None:
    conn = get_db()
    try:
        # Seed admin user (default creds)
        admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if not admin:
            pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt())
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("admin", pw_hash, utcnow_iso()),
            )
            conn.commit()

        admin_id = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()[0]

        # Seed a second user (owner of the flag export)
        other = conn.execute("SELECT id FROM users WHERE username = ?", ("casebot",)).fetchone()
        if not other:
            pw_hash = bcrypt.hashpw(b"R0tateMeLater!", bcrypt.gensalt())
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("casebot", pw_hash, utcnow_iso()),
            )
            conn.commit()
        casebot_id = conn.execute("SELECT id FROM users WHERE username = ?", ("casebot",)).fetchone()[0]

        # Seed admin's normal export at public_id=3
        exists_3 = conn.execute("SELECT 1 FROM exports WHERE public_id = ?", (SEED_USER_EXPORT_ID,)).fetchone()
        if not exists_3:
            payload = {
                "case_ref": "LF-2026-0142",
                "client": "Holloway & Pierce LLP",
                "matter": "Vendor dispute - arbitration prep",
                "rows": [
                    {"doc": "engagement_letter.pdf", "status": "signed", "updated": "2026-01-03"},
                    {"doc": "invoice_schedule.csv", "status": "generated", "updated": "2026-01-08"},
                    {"doc": "evidence_index.xlsx", "status": "draft", "updated": "2026-01-09"},
                ],
            }
            conn.execute(
                """
                INSERT INTO exports (public_id, owner_user_id, title, created_at, payload_json, debug_json)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (SEED_USER_EXPORT_ID, admin_id, "Client Case Export (Q1 Prep)", utcnow_iso(), json.dumps(payload)),
            )
            conn.commit()

        # Seed flag export at public_id=564 (belongs to casebot)
        exists_564 = conn.execute("SELECT 1 FROM exports WHERE public_id = ?", (SEED_FLAG_EXPORT_ID,)).fetchone()
        if not exists_564:
            payload = {
                "case_ref": "LF-2025-0991",
                "client": "Marrowline Holdings",
                "matter": "Regulatory review - confidential",
                "rows": [
                    {"doc": "case_roster.csv", "status": "archived", "updated": "2025-11-02"},
                    {"doc": "billing_summary.csv", "status": "archived", "updated": "2025-11-03"},
                ],
            }
            debug = {
                "build": "zipline-exporter/2.4.1",
                "notes": "Temporary debug attachment accidentally bundled in non-prod exports.",
                "internal": {
                    "base_url": f"http://{INTERNAL_SUBDOMAIN}",
                    "login": INTERNAL_LOGIN_URL,
                    "credentials": {
                        "username": INTERNAL_HINT_USER,
                        "password": INTERNAL_HINT_PASS,
                    },
                },
            }
            conn.execute(
                """
                INSERT INTO exports (public_id, owner_user_id, title, created_at, payload_json, debug_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (SEED_FLAG_EXPORT_ID, casebot_id, "Firmwide Case Archive (FY2025)", utcnow_iso(), json.dumps(payload), json.dumps(debug)),
            )
            conn.commit()

    finally:
        conn.close()


def make_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "uid": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=8)).timestamp()),
        "iss": "zipline-public",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def read_token_from_request(request: Request) -> Optional[dict]:
    token = request.cookies.get("zipline_token")
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()

    if not token:
        return None

    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def require_user(request: Request) -> sqlite3.Row:
    claims = read_token_from_request(request)
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")

    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (claims["uid"],)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Unknown user")
        return row
    finally:
        conn.close()


@app.on_event("startup")
def _startup():
    init_db()
    seed_data()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    claims = read_token_from_request(request)
    if claims:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "title": "Sign in", "subtitle": "Case Export Portal"},
    )


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip().lower()
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "title": "Sign in",
                    "subtitle": "Case Export Portal",
                    "error": "Invalid credentials.",
                    "hint": "If you’re onboarding in non-prod, use your default provisioned account.",
                },
                status_code=401,
            )

        token = make_token(user["id"], user["username"])
        resp = RedirectResponse("/dashboard", status_code=302)
        resp.set_cookie("zipline_token", token, httponly=True, samesite="lax")
        return resp
    finally:
        conn.close()


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("zipline_token")
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_user(request)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "username": user["username"],
            "api_base": API_BASE,
            "lab_domain": LAB_DOMAIN,
        },
    )


@app.get("/dashboard/exports", response_class=HTMLResponse)
def exports_page(request: Request):
    user = require_user(request)
    conn = get_db()
    try:
        exports = conn.execute(
            """
            SELECT public_id, title, created_at
            FROM exports
            WHERE owner_user_id = ?
            ORDER BY public_id DESC
            """,
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "exports.html",
        {"request": request, "title": "Exports", "username": user["username"], "exports": exports, "api_base": API_BASE},
    )


@app.get(f"{API_BASE}/exports")
def api_exports(request: Request):
    user = require_user(request)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT public_id, title, created_at FROM exports WHERE owner_user_id = ? ORDER BY public_id DESC",
            (user["id"],),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get(f"{API_BASE}/exports/{{public_id}}/download")
def api_export_download(request: Request, public_id: int):
    """
    VULNERABILITY (training): BOLA / IDOR
    - Requires authentication, but does NOT verify the export belongs to the current user.
    """
    _ = require_user(request)

    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM exports WHERE public_id = ?", (public_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Export not found")
    finally:
        conn.close()

    payload = json.loads(row["payload_json"] or "{}")
    debug = json.loads(row["debug_json"]) if row["debug_json"] else None

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("export.json", json.dumps(payload, indent=2))
        # realistic “artifact” file:
        csv_lines = ["doc,status,updated"]
        for r in payload.get("rows", []):
            csv_lines.append(f"{r.get('doc')},{r.get('status')},{r.get('updated')}")
        z.writestr("case_roster.csv", "\n".join(csv_lines))

        if debug:
            z.writestr("debug_attachment.json", json.dumps(debug, indent=2))

        z.writestr("README.txt", "Generated by Zipline Case Export Portal.\n")

    data = buf.getvalue()
    filename = f"zipline_export_{public_id}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
