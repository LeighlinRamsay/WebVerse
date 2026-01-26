# core/progress_db.py
import sqlite3
import time
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
    conn.commit()
    return conn

def mark_started(lab_id: str):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT started_at FROM progress WHERE lab_id=?", (lab_id,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO progress (lab_id, started_at, attempts) VALUES (?,?,0)",
                (lab_id, datetime.now(timezone.utc).isoformat())
            )
    _invalidate(lab_id)

def mark_attempt(lab_id: str):
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
