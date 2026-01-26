import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

APP_TITLE = "Tenant Tilt"
API_BASE = "/api/v1"

DB_PATH = os.getenv("DB_PATH", "/data/apiverse.db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-session-secret")

SEED_FLAG = os.getenv("SEED_FLAG", "WEBVERSE{t3n4nt_t1lt_1d0r_0wn3d}")
SEED_INVOICE_ID = int(os.getenv("SEED_INVOICE_ID", "564"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=APP_TITLE, version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


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
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                invoice_number TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                due_at TEXT NOT NULL,
                line_items_json TEXT NOT NULL,
                notes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_invoices_user_id ON invoices(user_id);
            CREATE INDEX IF NOT EXISTS idx_invoices_tenant_id ON invoices(tenant_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_flag_invoice() -> None:
    """
    Seed a separate tenant + user + a high-value invoice at a fixed ID.
    That invoice's notes contain the flag.
    """
    conn = get_db()
    try:
        exists = conn.execute("SELECT 1 FROM invoices WHERE id = ?", (SEED_INVOICE_ID,)).fetchone()
        if exists:
            return

        # Tenant
        conn.execute(
            "INSERT INTO tenants (name, created_at) VALUES (?, ?)",
            ("Nimbly Finance Group", utcnow_iso()),
        )
        tenant_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # User (not meant to be used, but real-looking)
        email = "ap@nimbl y-finance.example".replace(" ", "")
        password_hash = pwd_context.hash("Winter2026!ChangeMe")  # not exposed, just realistic
        conn.execute(
            "INSERT INTO users (tenant_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (tenant_id, email, password_hash, utcnow_iso()),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        issued = datetime.now(timezone.utc) - timedelta(days=7)
        due = datetime.now(timezone.utc) + timedelta(days=23)

        line_items = [
            {
                "sku": "ENT-ANNUAL-01",
                "description": "Enterprise Platform Renewal (Annual)",
                "qty": 1,
                "unit_price_cents": 299900,
                "total_cents": 299900,
            },
            {
                "sku": "SUPPORT-PLAT-01",
                "description": "Priority Support & Success (Annual)",
                "qty": 1,
                "unit_price_cents": 49900,
                "total_cents": 49900,
            },
        ]
        total_cents = sum(x["total_cents"] for x in line_items)

        notes = (
            "Internal: Customer requested invoice split into PO-backed line items. "
            "Routing via ACH for renewal.\n\n"
            f"Flag: {SEED_FLAG}\n"
        )

        conn.execute(
            """
            INSERT INTO invoices
                (id, tenant_id, user_id, title, invoice_number, amount_cents, currency, status,
                 issued_at, due_at, line_items_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SEED_INVOICE_ID,
                tenant_id,
                user_id,
                "Enterprise Renewal - Annual",
                "INV-2026-00564",
                total_cents,
                "USD",
                "unpaid",
                issued.isoformat(timespec="seconds"),
                due.isoformat(timespec="seconds"),
                json.dumps(line_items),
                notes,
                utcnow_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def on_startup():
    init_db()
    seed_flag_invoice()


def current_user(request: Request) -> Optional[sqlite3.Row]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    try:
        user = conn.execute(
            """
            SELECT u.*, t.name AS tenant_name
            FROM users u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()
        return user
    finally:
        conn.close()


def require_user(request: Request) -> sqlite3.Row:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "title": "Create account"})


@app.post("/signup")
def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if len(password) < 8:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "title": "Create account", "error": "Password must be at least 8 characters."},
            status_code=400,
        )

    conn = get_db()
    try:
        existing = conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return templates.TemplateResponse(
                "signup.html",
                {"request": request, "title": "Create account", "error": "Email already exists."},
                status_code=400,
            )

        # Create a tenant per signup (realistic “workspace” model)
        tenant_name = f"{email.split('@')[0].capitalize()}'s Workspace"
        conn.execute(
            "INSERT INTO tenants (name, created_at) VALUES (?, ?)",
            (tenant_name, utcnow_iso()),
        )
        tenant_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Create user
        password_hash = pwd_context.hash(password)
        conn.execute(
            "INSERT INTO users (tenant_id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (tenant_id, email, password_hash, utcnow_iso()),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Auto-create a subscription invoice for the new user
        issued = datetime.now(timezone.utc)
        due = issued + timedelta(days=14)
        line_items = [
            {
                "sku": "APV-SUB-MONTHLY",
                "description": "APIverse Subscription (Monthly)",
                "qty": 1,
                "unit_price_cents": 4900,
                "total_cents": 4900,
            }
        ]

        invoice_id = user_id + 1

        conn.execute(
            """
            INSERT INTO invoices
                (id, tenant_id, user_id, title, invoice_number, amount_cents, currency, status,
                 issued_at, due_at, line_items_json, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                tenant_id,
                user_id,
                "APIverse Subscription",
                f"INV-{issued.year}-{str(user_id).zfill(5)}",
                4900,
                "USD",
                "paid",
                issued.isoformat(timespec="seconds"),
                due.isoformat(timespec="seconds"),
                json.dumps(line_items),
                "Thank you for subscribing to APIverse.",
                utcnow_iso(),
            ),
        )

        conn.commit()

        request.session["user_id"] = user_id
        return RedirectResponse(url="/dashboard", status_code=302)
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
        user = conn.execute(
            """
            SELECT u.*, t.name AS tenant_name
            FROM users u
            JOIN tenants t ON t.id = u.tenant_id
            WHERE u.email = ?
            """,
            (email,),
        ).fetchone()

        if not user or not pwd_context.verify(password, user["password_hash"]):
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "title": "Sign in", "error": "Invalid email or password."},
                status_code=401,
            )

        request.session["user_id"] = user["id"]
        return RedirectResponse(url="/dashboard", status_code=302)
    finally:
        conn.close()


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "user_email": user["email"],
            "tenant_name": user["tenant_name"],
        },
    )


@app.get("/dashboard/invoices", response_class=HTMLResponse)
def invoices_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    conn = get_db()
    try:
        invoices = conn.execute(
            """
            SELECT id, title, invoice_number, amount_cents, currency, status, issued_at, due_at
            FROM invoices
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "invoices.html",
        {
            "request": request,
            "title": "Invoices",
            "user_email": user["email"],
            "tenant_name": user["tenant_name"],
            "invoices": invoices,
            "api_base": API_BASE,
        },
    )


# ------------------ API ------------------------

@app.get(f"{API_BASE}/me")
def api_me(request: Request):
    user = require_user(request)
    return {"email": user["email"], "tenant": user["tenant_name"]}


@app.get(f"{API_BASE}/invoices")
def api_invoices(request: Request):
    user = require_user(request)

    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT id, title, invoice_number, amount_cents, currency, status, issued_at, due_at
            FROM invoices
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user["id"],),
        ).fetchall()

        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get(f"{API_BASE}/invoices/{{invoice_id}}")
def api_invoice_by_id(request: Request, invoice_id: int):
    """
    VULNERABILITY (training): IDOR/BOLA
    - Authenticated users can fetch invoices by ID,
      but the endpoint does NOT verify ownership/tenant.
    """
    _ = require_user(request)

    conn = get_db()
    try:
        row = conn.execute(
            """
            SELECT
              i.id, i.title, i.invoice_number, i.amount_cents, i.currency, i.status,
              i.issued_at, i.due_at, i.line_items_json, i.notes,
              t.name AS tenant_name,
              u.email AS billed_to
            FROM invoices i
            JOIN tenants t ON t.id = i.tenant_id
            JOIN users u ON u.id = i.user_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")

        data = dict(row)
        data["line_items"] = json.loads(data.pop("line_items_json") or "[]")
        return JSONResponse(data)
    finally:
        conn.close()
