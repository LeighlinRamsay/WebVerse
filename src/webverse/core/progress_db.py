"""Cloud-backed progress with a locally-persisted device identity.

- The device UUID is stored locally in ~/.webverse/progress.db (sqlite), so the
  OSS app remains "device based" even without an account.
- Everything else (XP, rank, streak, per-lab progress, notes) is sourced from
  the public API (cloud) and derived from telemetry events.

This module keeps the same function names that the GUI already imports.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PyQt5.QtCore import QSettings

from webverse import __version__

# Persist all WebVerse data under ~/.webverse/
DATA_DIR = Path.home() / ".webverse"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "progress.db"

# ---- tiny in-process cache ----
_CACHE_TTL = 2.0  # seconds
_cache: dict = {
	"progress_blob": (0.0, None),  # (ts, dict from API)
	"progress_map": (0.0, None),   # (ts, dict)
	"summary": (0.0, None),        # (ts, dict)
	"recent": {},                  # limit -> (ts, rows)
	"notes": {},                   # lab_id -> (ts, notes)
	"stats": (0.0, None),          # (ts, DeviceStats)
	"device_linked": (0.0, None),  # (ts, bool)
}

def _ensure_cache_keys() -> None:
	"""
	Some flows previously used _cache.pop(...) which can break callers that
	index directly into _cache["progress_map"] etc.
	Make sure core keys always exist.
	"""
	defaults = {
		"progress_blob": (0.0, None),
		"progress_map": (0.0, None),
		"summary": (0.0, None),
		"recent": {},
		"notes": {},
		"stats": (0.0, None),
		"device_linked": (0.0, None),
	}
	for k, v in defaults.items():
		if k not in _cache:
			_cache[k] = v

class AuthRequiredError(RuntimeError):
	pass

class LoginGateError(RuntimeError):
	pass


def is_logged_in() -> bool:
	s = _settings()
	tok = str(s.value("auth/access_token", "") or "").strip()
	return bool(tok)


def _with_retries(fn, *, retries: int = 3, backoff_s: float = 0.20):
	err: Exception | None = None
	for i in range(max(1, int(retries))):
		try:
			return fn()
		except Exception as e:
			err = e
			# quick exponential backoff
			try:
				time.sleep(float(backoff_s) * (1.6 ** i))
			except Exception:
				pass
	if err:
		raise err
	raise RuntimeError("request failed")


def _now() -> float:
	return time.monotonic()


def _fresh(ts: float, max_age_s: Optional[float] = None) -> bool:
	"""
	Cache freshness helper.
	- default TTL: _CACHE_TTL
	- caller can override with max_age_s (e.g. profile cache)
	"""
	ttl = _CACHE_TTL if max_age_s is None else float(max_age_s)
	return (_now() - float(ts)) <= ttl


def _invalidate(lab_id: Optional[str] = None) -> None:
	_cache["progress_blob"] = (0.0, None)
	_cache["progress_map"] = (0.0, None)
	_cache["summary"] = (0.0, None)
	_cache["recent"].clear()
	if lab_id is not None:
		_cache["notes"].pop(str(lab_id), None)
	_cache["stats"] = (0.0, None)
	# also drop auth-backed caches so XP/rank/solves refresh immediately after events
	try:
		_cache.pop("profile", None)
		_cache.pop("activity_first", None)
	except Exception:
		pass

def invalidate_cache(*, lab_id: Optional[str] = None) -> None:
	"""
	Public hook for UI code.
	Use this when auth state changes (login/logout) or when you need
	to force the next read to hit the API immediately.
	"""
	_invalidate(lab_id=lab_id)

def on_auth_changed() -> None:
	invalidate_cache()


def connect() -> sqlite3.Connection:
	"""Local sqlite used ONLY for device identity + small flags."""
	conn = sqlite3.connect(DB_PATH)
	conn.execute("PRAGMA journal_mode=WAL;")
	conn.execute("PRAGMA synchronous=NORMAL;")

	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS device (
			id TEXT PRIMARY KEY,
			created_at TEXT,
			first_seen_sent INTEGER DEFAULT 0
		)
		"""
	)

	cur = conn.cursor()
	cur.execute("PRAGMA table_info(device)")
	cols = {row[1] for row in cur.fetchall()}
	if "first_seen_sent" not in cols:
		try:
			conn.execute("ALTER TABLE device ADD COLUMN first_seen_sent INTEGER DEFAULT 0")
		except Exception:
			pass

	cur.execute("SELECT id FROM device LIMIT 1")
	row = cur.fetchone()
	if not row:
		did = str(uuid.uuid4())
		conn.execute(
			"INSERT INTO device (id, created_at, first_seen_sent) VALUES (?,?,0)",
			(did, datetime.now(timezone.utc).isoformat()),
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
		conn.execute("UPDATE device SET first_seen_sent=?", (1 if sent else 0,))
		conn.commit()


def _api_base() -> str:
	return (
		os.getenv("WEBVERSE_API_BASE_URL", os.getenv("WEBVERSE_API_URL", "https://api-opensource.webverselabs.com"))
		or ""
	).rstrip("/")


def _timeout() -> float:
	try:
		return float(os.getenv("WEBVERSE_API_TIMEOUT", "6") or 6)
	except Exception:
		return 6.0


def _settings() -> QSettings:
	return QSettings("WebVerse", "WebVerse")

def _device_linked_cache_ttl_s() -> float:
	return 30.0

def is_device_linked(*, force: bool = False) -> bool:
	"""
	Checks server-side whether this device_id is linked to any account.
	Cached briefly to avoid spamming.
	"""
	ts, cached = _cache.get("device_linked", (0.0, None))
	if (not force) and cached is not None and _fresh(ts, max_age_s=_device_linked_cache_ttl_s()):
		return bool(cached)

	base = _api_base()
	did = get_device_id()
	out = _safe_request_json("GET", f"{base}/v1/auth/device-linked/{did}", auth=False) or {}
	linked = bool(out.get("linked") is True)
	_cache["device_linked"] = (_now(), linked)
	return linked

def requires_login_gate(*, force: bool = False) -> bool:
	"""
	If the device is linked to an account, the app must be logged in.
	"""
	try:
		if is_logged_in():
			return False
		return bool(is_device_linked(force=force))
	except Exception:
		# Fail open on connectivity issues; don't brick offline users.
		return False

def _clear_auth_state() -> None:
	"""
	If the server rejects /v1/auth/me with 401, the local token is invalid.
	Clear auth state so the UI shows Signup/Login instead of the profile badge.
	"""
	try:
		s = _settings()
		s.setValue("auth/access_token", "")
		s.setValue("auth/refresh_token", "")
		s.setValue("auth/username", "")
		s.setValue("auth/email", "")
		s.setValue("auth/xp", 0)
		s.setValue("auth/rank", "")
		s.sync()
	except Exception:
		pass
	_invalidate()

def clear_everything_on_logout(*, keep_device_id: bool = True) -> None:
	"""
	Clears ALL local auth + cached state.
	Keeps device_id by default so device linkage still works.
	"""
	try:
		s = _settings()
		try:
			keys = list(s.allKeys())
		except Exception:
			keys = []

		for k in keys:
			try:
				# Keep device identity (stored in sqlite), not QSettings
				s.remove(k)
			except Exception:
				pass

		try:
			s.sync()
		except Exception:
			pass
	except Exception:
		pass

	# In-memory caches
	_invalidate()
	try:
		_cache["device_linked"] = (0.0, None)
	except Exception:
		pass

def logout_remote_best_effort() -> None:
	"""
	Calls /v1/auth/logout (token_version bump) if we have a token.
	Never raises.
	"""
	tok = _auth_token()
	if not tok:
		return
	base = _api_base()
	try:
		_safe_request_json("POST", f"{base}/v1/auth/logout", {}, auth=True)
	except Exception:
		pass

def _auth_token() -> str:
	s = _settings()
	return str(s.value("auth/access_token", "") or "").strip()


def _request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None, *, auth: bool = False) -> Dict[str, Any]:
	headers = {
		"Accept": "application/json",
		"User-Agent": f"WebVerse-OSS/{__version__}",
	}
	if payload is not None:
		headers["Content-Type"] = "application/json"

	if auth:
		tok = _auth_token()
		if tok:
			headers["Authorization"] = f"Bearer {tok}"

	data = None
	if payload is not None:
		data = json.dumps(payload).encode("utf-8")

	req = urllib.request.Request(url=url, data=data, headers=headers, method=method.upper())
	try:
		with urllib.request.urlopen(req, timeout=_timeout()) as resp:
			raw = resp.read().decode("utf-8") or "{}"
			try:
				out = json.loads(raw)
				return out if isinstance(out, dict) else {}
			except Exception:
				return {}
	except urllib.error.HTTPError as e:
		# If /v1/auth/me says unauthorized, our local token is stale.
		# Clear auth state so the app returns to "logged out" UI.
		try:
			if auth and int(getattr(e, "code", 0) or 0) == 401:
				_clear_auth_state()
				_invalidate()
		except Exception:
			pass
		raise


def _safe_request_json(method: str, url: str, payload: Optional[Dict[str, Any]] = None, *, auth: bool = False) -> Dict[str, Any]:
	try:
		return _request_json(method, url, payload, auth=auth)
	except urllib.error.HTTPError:
		return {}

def _request_json_with_retries(
   method: str,
   url: str,
   payload: Optional[Dict[str, Any]] = None,
   *,
   auth: bool = False,
   retries: int = 3,
   backoff_s: float = 0.22,
) -> Dict[str, Any]:
   """Like _safe_request_json but raises after retries."""
   last_err: Exception | None = None
   for i in range(max(1, int(retries))):
	   try:
		   out = _safe_request_json(method, url, payload, auth=auth)
		   if out is None:
			   out = {}
		   # If auth was required and token is missing or cleared, treat as auth required.
		   if auth and not _auth_token():
			   raise AuthRequiredError("Not authenticated")
		   return out
	   except AuthRequiredError as e:
		   last_err = e
		   break
	   except Exception as e:
		   last_err = e
		   if i < retries - 1:
			   time.sleep(backoff_s * (1.6 ** i))
			   continue
		   break
   if last_err:
	   raise last_err
   return {}


def invalidate_remote_cache() -> None:
	"""Called when auth changes (login/logout) so UI doesn't show stale data."""
	_ensure_cache_keys()
	# Never pop core keys that other code indexes directly.
	for k in ("stats", "progress_blob", "progress_map", "summary"):
		try:
			_cache[k] = (0.0, None)
		except Exception:
			pass
	for k in ("profile", "activity_first"):
		try:
			_cache.pop(k, None)
		except Exception:
			pass


def fetch_profile(*, force: bool = False, retries: int = 3) -> Dict[str, Any]:
   """Fetch /v1/auth/me with retries.

   Cached for a very short interval so repeated UI paints don't spam the API.
   """
   ts, cached = _cache.get("profile", (0.0, None))
   if not force and cached is not None and _fresh(ts, max_age_s=8.0):
	   return dict(cached)

   if not is_logged_in():
	   raise AuthRequiredError("Not authenticated")

   base = _api_base()
   out = _request_json_with_retries("GET", f"{base}/v1/auth/me", auth=True, retries=retries)
   if not isinstance(out, dict):
	   out = {}
   _cache["profile"] = (_now(), dict(out))
   return dict(out)


def fetch_activity_me_page(*, cursor: Optional[int] = None, limit: int = 25, retries: int = 3) -> Dict[str, Any]:
   """Fetch one page from /v1/activity/me with retries."""
   if not is_logged_in():
	   raise AuthRequiredError("Not authenticated")

   base = _api_base()
   q = f"?limit={int(limit)}"
   if cursor is not None:
	   q += f"&cursor={int(cursor)}"
   out = _request_json_with_retries("GET", f"{base}/v1/activity/me{q}", auth=True, retries=retries)
   if not isinstance(out, dict):
	   out = {}
   return out


@dataclass
class DeviceStats:
	xp: int = 0
	rank: str = "Recruit"
	next_rank: Optional[str] = None
	next_rank_xp: Optional[int] = None
	streak_days: int = 0
	labs_solved: int = 0
	labs_started: int = 0


def get_device_stats(*, force: bool = False) -> DeviceStats:
	ts, cached = _cache.get("stats", (0.0, None))
	if not force and cached is not None and _fresh(ts):
		return cached

	# If this device is linked, and the user is logged out, we should NOT
	# surface device-backed stats (prevents "lingering" personal progress on Home).
	try:
		if requires_login_gate(force=False) and (not is_logged_in()):
			stats = DeviceStats()
			_cache["stats"] = (_now(), stats)
			return stats
	except Exception:
		pass

	base = _api_base()
	out: Dict[str, Any] = {}

	tok = _auth_token()
	if tok:
		out = _safe_request_json("GET", f"{base}/v1/auth/me", auth=True) or {}

	if not out or ("xp" not in out and "rank" not in out):
		did = get_device_id()
		out = _safe_request_json("GET", f"{base}/v1/stats/device/{did}") or {}

	stats = DeviceStats(
		xp=int(out.get("xp") or 0),
		rank=str(out.get("rank") or "Recruit"),
		next_rank=(str(out.get("next_rank")) if out.get("next_rank") else None),
		next_rank_xp=(int(out.get("next_rank_xp")) if out.get("next_rank_xp") is not None else None),
		streak_days=int(out.get("streak_days") or 0),
		labs_solved=int(out.get("labs_solved") or 0),
		labs_started=int(out.get("labs_started") or 0),
	)

	# Only persist auth/xp/rank when actually authenticated (prevents repopulating after logout).
	try:
		if is_logged_in():
			s = _settings()
			s.setValue("auth/xp", int(stats.xp))
			s.setValue("auth/rank", stats.rank)
	except Exception:
		pass

	_cache["stats"] = (_now(), stats)
	return stats


def mark_started(lab_id: str, difficulty: str | None = None):
	_invalidate(str(lab_id))
	try:
		from webverse.core.usercounter import send_event
		props = {"lab_id": str(lab_id)}
		if difficulty:
			props["difficulty"] = str(difficulty)
		send_event("lab_started", props)
	except Exception:
		pass


def mark_attempt(lab_id: str):
	_invalidate(str(lab_id))
	try:
		from webverse.core.usercounter import send_event
		send_event("lab_attempt", {"lab_id": str(lab_id)})
	except Exception:
		pass


def mark_solved(lab_id: str, difficulty: str | None = None):
	_invalidate(str(lab_id))
	try:
		from webverse.core.usercounter import send_event
		props = {"lab_id": str(lab_id)}
		if difficulty:
			props["difficulty"] = str(difficulty)
		send_event("lab_solved", props)
	except Exception:
		pass

def submit_flag(lab_id: str, flag: str) -> Tuple[bool, str, Dict[str, Any]]:
	"""
	Server-side solve flow.
	Returns (ok, error_message, meta).
	meta is best-effort and may include keys like: xp_awarded, newly_solved, difficulty, lab_id.
	"""
	lab_id = str(lab_id or "").strip()
	flag = str(flag or "").strip()
	if not lab_id:
		return (False, "Invalid lab_id.", {})
	if not flag:
		return (False, "Empty flag.", {})

	base = _api_base()
	did = get_device_id()

	payload = {
		"device_id": did,
		"lab_id": lab_id,
		"flag": flag,
		"app_version": __version__,
	}

	out = _safe_request_json("POST", f"{base}/v1/labs/submit-flag", payload, auth=False) or {}
	if bool(out.get("ok") is True):
		_invalidate(lab_id)
		meta: Dict[str, Any] = {}
		try:
			meta["lab_id"] = str(out.get("lab_id") or lab_id)
			meta["difficulty"] = str(out.get("difficulty") or "")
			meta["newly_solved"] = bool(out.get("newly_solved") is True)
			meta["xp_awarded"] = int(out.get("xp_awarded") or 0)
		except Exception:
			meta = {}
		return (True, "", meta)

	msg = str(out.get("error") or out.get("detail") or "Invalid flag.")
	return (False, msg, {})


def _fetch_progress_blob(*, force: bool = False) -> Dict[str, Any]:
	ts, cached = _cache.get("progress_blob", (0.0, None))
	if (not force) and cached is not None and _fresh(ts):
		return dict(cached)

	# Same rule as stats: if device is linked but user is logged out, don't fetch
	# progress from device endpoints (prevents showing solves/attempts while logged out).
	try:
		if requires_login_gate(force=False) and (not is_logged_in()):
			_cache["progress_blob"] = (_now(), {})
			return {}
	except Exception:
		pass

	base = _api_base()
	did = get_device_id()
	blob = _safe_request_json("GET", f"{base}/v1/progress/device/{did}") or {}
	if not isinstance(blob, dict):
		blob = {}
	_cache["progress_blob"] = (_now(), blob)
	return dict(blob)


def get_progress_map(*, force: bool = False):
	_ensure_cache_keys()
	ent = _cache.get("progress_map", (0.0, None))
	try:
		ts, data = ent
	except Exception:
		ts, data = (0.0, None)

	if (not force) and data is not None and _fresh(ts):
		return {k: dict(v) for k, v in data.items()}

	blob = _fetch_progress_blob(force=force)
	progress = blob.get("progress") or {}
	if not isinstance(progress, dict):
		progress = {}

	out: Dict[str, Dict[str, Any]] = {}
	for lab_id, p in progress.items():
		if not lab_id:
			continue
		row = p if isinstance(p, dict) else {}
		out[str(lab_id)] = {
			"started_at": row.get("started_at"),
			"solved_at": row.get("solved_at"),
			"attempts": int(row.get("attempts") or 0),
			"notes": str(row.get("notes") or ""),
		}

	_cache["progress_map"] = (_now(), out)
	return {k: dict(v) for k, v in out.items()}


def get_summary():
	_ensure_cache_keys()
	ts, data = _cache.get("summary", (0.0, None))
	if data is not None and _fresh(ts):
		return dict(data)

	blob = _fetch_progress_blob()
	summary = blob.get("summary") or {}
	if not isinstance(summary, dict):
		summary = {}

	out = {
		"started": int(summary.get("started") or 0),
		"solved": int(summary.get("solved") or 0),
		"attempts": int(summary.get("attempts") or 0),
	}
	_cache["summary"] = (_now(), out)
	return dict(out)


def get_recent(limit=10):
	limit = int(limit or 10)
	ent = _cache["recent"].get(limit)
	if ent is not None:
		ts, rows = ent
		if rows is not None and _fresh(ts):
			return list(rows)

	blob = _fetch_progress_blob()
	rows = blob.get("recent") or []
	if not isinstance(rows, list):
		rows = []

	out = []
	for r in rows[:limit]:
		if not isinstance(r, dict):
			continue
		out.append(
			{
				"lab_id": str(r.get("lab_id") or ""),
				"started_at": r.get("started_at"),
				"solved_at": r.get("solved_at"),
				"attempts": int(r.get("attempts") or 0),
			}
		)

	_cache["recent"][limit] = (_now(), out)
	return list(out)


def get_notes(lab_id: str) -> str:
	lab_id = str(lab_id)
	ent = _cache["notes"].get(lab_id)
	if ent is not None:
		ts, notes = ent
		if notes is not None and _fresh(ts):
			return str(notes)

	try:
		pm = get_progress_map()
		if lab_id in pm:
			notes = str(pm[lab_id].get("notes") or "")
			_cache["notes"][lab_id] = (_now(), notes)
			return notes
	except Exception:
		pass

	base = _api_base()
	did = get_device_id()
	out = _safe_request_json("GET", f"{base}/v1/notes/device/{did}/{lab_id}") or {}
	notes = str(out.get("notes") or "")
	_cache["notes"][lab_id] = (_now(), notes)
	return notes


def set_notes(lab_id: str, notes: str):
	lab_id = str(lab_id)
	base = _api_base()
	did = get_device_id()
	_safe_request_json("POST", f"{base}/v1/notes/device/{did}/{lab_id}", {"notes": notes or ""})
	_cache["notes"][lab_id] = (_now(), str(notes or ""))
	_invalidate(lab_id)