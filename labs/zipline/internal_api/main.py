import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

DB_PATH = os.getenv("DB_PATH", "/data/internal.db")
JWT_SECRET = os.getenv("INTERNAL_JWT_SECRET", "internal-dev-secret")

INTERNAL_USER = os.getenv("INTERNAL_USER", "svc-exporter")
INTERNAL_PASS = os.getenv("INTERNAL_PASS", "Spring2026!RotateMe")
FLAG = os.getenv("FLAG", "WEBVERSE{missing-flag}")

app = FastAPI(title="Zipline Internal API", version="2.0.0", docs_url=None, redoc_url=None)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
            CREATE TABLE IF NOT EXISTS service_users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE,
              password_hash BLOB NOT NULL,
              role TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_user() -> None:
    conn = get_db()
    try:
        row = conn.execute("SELECT 1 FROM service_users WHERE username = ?", (INTERNAL_USER,)).fetchone()
        if row:
            return
        pw_hash = bcrypt.hashpw(INTERNAL_PASS.encode("utf-8"), bcrypt.gensalt())
        conn.execute(
            "INSERT INTO service_users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (INTERNAL_USER, pw_hash, "integration", utcnow().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def _startup():
    init_db()
    seed_user()


def make_token(uid: int, username: str, role: str) -> str:
    now = utcnow()
    payload = {
        "username": username,
        "userid": uid,
        "role": role,
        "iat": int(now.timestamp()),
        "ext": int((now + timedelta(minutes=30)).timestamp()),
        "iss": "zipline-internal",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def require_token(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.split(" ", 1)[1].strip()
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/api/v2/user/login")
async def login(body: dict):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()

    conn = get_db()
    try:
        u = conn.execute("SELECT * FROM service_users WHERE username = ?", (username,)).fetchone()
        if not u or not bcrypt.checkpw(password.encode("utf-8"), u["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = make_token(u["id"], u["username"], u["role"])
        return {"access_token": token, "token_type": "bearer"}
    finally:
        conn.close()


@app.get("/api/v2/user/me")
def me(request: Request):
    claims = require_token(request)
    return {"ok": True, "claims": {"username": claims.get("username"), "role": claims.get("role")}}


@app.get("/api/v2/user/config")
def config(request: Request):
    _ = require_token(request)
    return JSONResponse(
        {
            "service": "zipline-internal",
            "env": "staging",
            "secrets": {
                "flag": FLAG,
                "export_signing_key": "KMS_DISABLED_DEVKEY",
                "webhook_secret": "whsec_dev_4f91c8a2",
            },
            "internal": {
                "notes": "Do not expose this API publicly. Restricted to internal routing.",
            },
        }
    )
