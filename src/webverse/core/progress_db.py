# core/progress_db.py
import sqlite3
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Persist all WebVerse data under ~/.webverse/
DATA_DIR = Path.home() / ".webverse"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "progress.db"

# ---- tiny in-process cache ----
# The GUI calls progress_map/summary frequently (table refresh, badges, etc.).
# Cache reads briefly and invalidate on writes to keep UI snappy.
_CACHE_TTL = 0.75  # seconds
_cache = {
    "progress_map": (0.0, None),  # (ts, dict)
    "summary": (0.0, None),       # (ts, dict)
    "recent": {},                 # limit -> (ts, rows)
    "notes": {},                  # lab_id -> (ts, notes)
}


def _now() -> float:
    return time.monotonic()


def _fresh(ts: float) -> bool:
    return (_now() - float(ts)) <= _CACHE_TTL


def _invalidate(lab_id: Optional[str] = None) -> None:
    _cache["progress_map"] = (0.0, None)
    _cache["summary"] = (0.0, None)
    _cache["recent"].clear()
    if lab_id is not None:
        _cache["notes"].pop(str(lab_id), None)

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS progress (
        lab_id TEXT PRIMARY KEY,
        started_at TEXT,
        solved_at TEXT,
        attempts INTEGER DEFAULT 0
    )
    """)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(progress)")
    cols = {row[1] for row in cur.fetchall()}
    if "notes" not in cols:
        conn.execute("ALTER TABLE progress ADD COLUMN notes TEXT DEFAULT ''")

    # ---- device identity (anonymous) ----
    conn.execute("""
    CREATE TABLE IF NOT EXISTS device (
        id TEXT PRIMARY KEY,
        created_at TEXT,
        first_seen_sent INTEGER DEFAULT 0
    )
    """)

    cur = conn.cursor()
    cur.execute("PRAGMA table_info(device)")
    dev_cols = {row[1] for row in cur.fetchall()}
    if "first_seen_sent" not in dev_cols:
        conn.execute("ALTER TABLE device ADD COLUMN first_seen_sent INTEGER DEFAULT 0")

    cur.execute("SELECT id FROM device LIMIT 1")
    row = cur.fetchone()
    if not row:
        did = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO device (id, created_at, first_seen_sent) VALUES (?,?,0)",
            (did, datetime.now(timezone.utc).isoformat())
        )

    conn.commit()
    return conn

def get_device_id() -> str:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM device LIMIT 1")
        row = cur.fetchone()
        return str(row[0])


def get_first_seen_sent() -> bool:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(first_seen_sent,0) FROM device LIMIT 1")
        row = cur.fetchone()
        return bool(int(row[0] or 0))


def set_first_seen_sent(sent: bool = True) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE device SET first_seen_sent=?",
            (1 if sent else 0,)
        )
        conn.commit()

def mark_started(lab_id: str):
    """
    Record that the user successfully STARTED this lab.

    NOTE: `started_at` is treated as the most recent successful start time
    (used for "Active" state + uptime). We do NOT increment attempts here.
    Attempts are counted when the user later STOPS the lab without solving.
    """
    ts = datetime.now(timezone.utc).isoformat()

    with connect() as conn:
        cur = conn.cursor()
        # Ensure row exists, then update latest start timestamp.
        cur.execute(
            "INSERT OR IGNORE INTO progress (lab_id, started_at, attempts) VALUES (?,?,0)",
            (lab_id, ts)
        )
        cur.execute("UPDATE progress SET started_at=? WHERE lab_id=?", (ts, lab_id))
    _invalidate(lab_id)
    
    # Best-effort telemetry (never blocks, never breaks the app)
    try:
        from webverse.core.usercounter import send_event
        send_event("lab_started", {"lab_id": lab_id})
    except Exception:
        pass

def mark_attempt(lab_id: str):
    """
    Increment attempts when the user STOPPED a running lab without solving it.
    This matches: "how many times has the user started this lab then stopped it
    without submitting the flag."
    """

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT attempts FROM progress WHERE lab_id=?", (lab_id,))
        row = cur.fetchone()
        if not row:
            cur.execute("INSERT INTO progress (lab_id, attempts) VALUES (?,1)", (lab_id,))
        else:
            cur.execute("UPDATE progress SET attempts=attempts+1 WHERE lab_id=?", (lab_id,))
    _invalidate(lab_id)

def mark_solved(lab_id: str):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT solved_at FROM progress WHERE lab_id=?", (lab_id,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO progress (lab_id, solved_at) VALUES (?,?)",
                (lab_id, datetime.now(timezone.utc).isoformat())
            )
        elif not row[0]:
            cur.execute(
                "UPDATE progress SET solved_at=? WHERE lab_id=?",
                (datetime.now(timezone.utc).isoformat(), lab_id)
            )
    _invalidate(lab_id)
    
    # Best-effort telemetry (never blocks, never breaks the app)
    try:
        from webverse.core.usercounter import send_event
        send_event("lab_solved", {"lab_id": lab_id})
    except Exception:
        pass

def get_progress_map():
    ts, data = _cache["progress_map"]
    if data is not None and _fresh(ts):
        # defensive copy so callers don't mutate cached dict
        return {k: dict(v) for k, v in data.items()}

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT lab_id, started_at, solved_at, COALESCE(attempts,0), COALESCE(notes,'')
            FROM progress
        """)
        rows = cur.fetchall()

    out = {}
    for lab_id, started_at, solved_at, attempts, notes in rows:
        out[lab_id] = {
            "started_at": started_at,
            "solved_at": solved_at,
            "attempts": int(attempts or 0),
            "notes": (notes or ""),
        }
    _cache["progress_map"] = (_now(), out)
    return out

def get_summary():
    ts, data = _cache["summary"]
    if data is not None and _fresh(ts):
        return dict(data)

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM progress WHERE started_at IS NOT NULL")
        started = cur.fetchone()[0] or 0

        cur.execute("SELECT COUNT(*) FROM progress WHERE solved_at IS NOT NULL")
        solved = cur.fetchone()[0] or 0

        cur.execute("SELECT COALESCE(SUM(attempts),0) FROM progress")
        attempts = cur.fetchone()[0] or 0

    out = {"started": int(started), "solved": int(solved), "attempts": int(attempts)}
    _cache["summary"] = (_now(), out)
    return dict(out)

def get_recent(limit=10):
    limit = int(limit or 10)
    ent = _cache["recent"].get(limit)
    if ent is not None:
        ts, rows = ent
        if rows is not None and _fresh(ts):
            return list(rows)

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("""
          SELECT lab_id, started_at, solved_at, COALESCE(attempts,0)
          FROM progress
          ORDER BY COALESCE(solved_at, started_at) DESC
          LIMIT ?
        """, (limit,))
        rows = cur.fetchall()

    out = [
        {"lab_id": r[0], "started_at": r[1], "solved_at": r[2], "attempts": int(r[3] or 0)}
        for r in rows
    ]
    _cache["recent"][limit] = (_now(), out)
    return list(out)


def get_notes(lab_id: str) -> str:
    lab_id = str(lab_id)
    ent = _cache["notes"].get(lab_id)
    if ent is not None:
        ts, notes = ent
        if notes is not None and _fresh(ts):
            return str(notes)

    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(notes,'') FROM progress WHERE lab_id=?", (lab_id,))
        row = cur.fetchone()
    notes = (row[0] if row else "") or ""
    _cache["notes"][lab_id] = (_now(), notes)
    return notes


def set_notes(lab_id: str, notes: str):
    lab_id = str(lab_id)
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO progress (lab_id, attempts) VALUES (?, 0)", (lab_id,))
        cur.execute("UPDATE progress SET notes=? WHERE lab_id=?", ((notes or ""), lab_id))
    _invalidate(lab_id)
