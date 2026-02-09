# gui/app_state.py
from __future__ import annotations

import hashlib
import threading
import time
from typing import Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from webverse.core.registry import discover_labs
from webverse.core.runtime import get_running_lab, set_running_lab
from webverse.core.docker_ops import docker_available, compose_v2_available, compose_has_running
from webverse.core.models import Lab

from webverse.core import progress_db


class AppState(QObject):
	labs_changed = pyqtSignal()
	filter_changed = pyqtSignal(str)
	selected_changed = pyqtSignal(object)  # Lab|None
	running_changed = pyqtSignal(object)   # Lab|None
	docker_changed = pyqtSignal(str, str)  # text, kind
	log_line = pyqtSignal(str)
	progress_changed = pyqtSignal()        # progress/notes updated (refresh badges, stats, etc.)
	player_stats_changed = pyqtSignal()    # XP/rank/stats updated from API
	runtime_op_changed = pyqtSignal(str, str)  # lab_id, op (starting|stopping|resetting|running|stopped)

	def __init__(self):
		super().__init__()
		self._labs: List[Lab] = []
		self._filter: str = ""
		self._selected: Optional[Lab] = None
		self._running_lab_id: Optional[str] = get_running_lab()
		self._docker_text: str = "Docker: Unknown"
		self._docker_kind: str = "neutral"

		self._runtime_op: str = "stopped"
		self._runtime_op_lab_id: Optional[str] = None

		# ---- Progress/Notes caches (avoid repeated SQLite reads) ----
		self._progress_cache: Optional[Dict[str, dict]] = None
		self._progress_dirty: bool = True
		self._summary_cache: Optional[dict] = None
		self._summary_dirty: bool = True
		self._notes_cache: Dict[str, str] = {}

		self.refresh_labs()
		self.refresh_docker()
		self._verify_runtime_running_lab()

	def on_auth_changed(self) -> None:
		"""
		Called on login/logout/account switch.

		Goals:
		- Drop any cached stats/progress that may have been computed pre-login.
		- Force all UI surfaces (Home, sidebar badge, Progress page, etc.) to repaint.
		"""
		# 1) Invalidate progress_db's tiny in-process cache so /v1/auth/me is re-read.
		try:
			if hasattr(progress_db, "on_auth_changed"):
				progress_db.on_auth_changed()
			elif hasattr(progress_db, "invalidate_cache"):
				progress_db.invalidate_cache()
			elif hasattr(progress_db, "invalidate_remote_cache"):
				progress_db.invalidate_remote_cache()
		except Exception:
			pass

		# 2) Drop AppState's own cached views of progress/summary/notes.
		try:
			self._progress_cache = None
			self._progress_dirty = True
		except Exception:
			pass
		try:
			self._summary_cache = None
			self._summary_dirty = True
		except Exception:
			pass
		try:
			self._notes_cache = {}
		except Exception:
			pass

		# 3) Broadcast repaint signals (Home listens to these).
		try:
			self.player_stats_changed.emit()
		except Exception:
			pass
		try:
			self.progress_changed.emit()
		except Exception:
			pass
		try:
			self.labs_changed.emit()
		except Exception:
			pass

	# ---- Cache invalidation ----
	def _invalidate_progress(self) -> None:
		self._progress_dirty = True
		# do not wipe cache dict immediately; keep it for potential reads until refreshed

	def _invalidate_summary(self) -> None:
		self._summary_dirty = True

	def _invalidate_all_progress_views(self) -> None:
		self._invalidate_progress()
		self._invalidate_summary()
		self.progress_changed.emit()

	def clear_user_caches(self) -> None:
		"""
		Clear all API-backed caches (progress map, summary, notes) so UI can
		immediately reflect a logout or account switch.
		"""
		try:
			self._progress_cache = None
			self._progress_dirty = True
		except Exception:
			pass
		try:
			self._summary_cache = None
			self._summary_dirty = True
		except Exception:
			pass
		try:
			self._notes_cache = {}
		except Exception:
			pass
		# Force all dependent UI surfaces to refresh
		try:
			self.player_stats_changed.emit()
		except Exception:
			pass
		try:
			self.progress_changed.emit()
		except Exception:
			pass
		try:
			self.labs_changed.emit()
		except Exception:
			pass

	def _refresh_player_stats_async(self, *, expect_solved_increment: bool = False, prev_labs_solved: int = 0) -> None:
		"""Force-refresh XP/rank/stats from the API and notify the UI.

		We do this async because the API update is event-driven (telemetry).
		After a solve event we may need a short moment for the server to apply
		the XP + labs_solved updates.
		"""

		def _bg():
			try:
				attempts = 4 if expect_solved_increment else 2
				delay = 0.18
				got = None
				for _ in range(max(1, attempts)):
					got = progress_db.get_device_stats(force=True)
					if expect_solved_increment:
						try:
							if int(getattr(got, "labs_solved", 0) or 0) >= int(prev_labs_solved) + 1:
								break
						except Exception:
							pass
					time.sleep(delay)
					delay = min(1.0, delay * 1.8)
			except Exception:
				# Don't crash the UI if the network is down.
				pass

			try:
				from PyQt5.QtCore import QTimer
				QTimer.singleShot(0, self._emit_player_stats_changed)
			except Exception:
				# If Qt isn't ready, just best-effort emit directly.
				try:
					self._emit_player_stats_changed()
				except Exception:
					pass

		threading.Thread(target=_bg, daemon=True).start()

	def _emit_player_stats_changed(self) -> None:
		# Ensure *all* stat surfaces update: sidebar badge, progress, etc.
		try:
			self.player_stats_changed.emit()
		except Exception:
			pass
		try:
			self.progress_changed.emit()
		except Exception:
			pass

	def set_runtime_op(self, op: str, lab_id: Optional[str] = None) -> None:
		"""
		Broadcast a transient runtime operation so the TopBar pill can reflect:
		  starting (green), stopping (red), resetting (yellow), running, stopped.
		"""
		op = (op or "").strip().lower() or "stopped"
		if op not in ("starting", "stopping", "resetting", "running", "stopped"):
			op = "stopped"

		# HARD GUARD:
		# Never allow some other lab (often via navigation) to clobber an in-flight transient op.
		try:
			cur_op = (self._runtime_op or "").strip().lower()
			cur_lid = str(self._runtime_op_lab_id) if self._runtime_op_lab_id else ""
			new_lid = str(lab_id) if lab_id else ""

			if cur_op in ("starting", "stopping", "resetting") and cur_lid:
				# Another lab trying to become transient while one is already transient -> ignore.
				if op in ("starting", "stopping", "resetting") and new_lid and new_lid != cur_lid:
					return
				# Another lab trying to clear transient op -> ignore (unless clearing with no lab_id).
				if op == "stopped" and new_lid and new_lid != cur_lid:
					return
		except Exception:
			pass

		self._runtime_op = op
		self._runtime_op_lab_id = str(lab_id) if (lab_id and op != "stopped") else None
		try:
			self.runtime_op_changed.emit(str(self._runtime_op_lab_id or ""), op)
		except Exception:
			pass

	def runtime_op_for(self, lab_id: Optional[str]) -> str:
		"""
		Best-effort current state for a specific lab:
		- if a transient op is active for this lab: starting/stopping/resetting
		- else: running if this lab is the running lab
		- else: stopped
		"""
		lid = str(lab_id) if lab_id else ""
		if lid and self._runtime_op_lab_id and lid == str(self._runtime_op_lab_id):
			if self._runtime_op in ("starting", "stopping", "resetting"):
				return self._runtime_op
		if lid and self._running_lab_id and lid == str(self._running_lab_id):
			return "running"
		return "stopped"

	def runtime_op_lab_id(self) -> Optional[str]:
		"""
		Expose the lab_id currently associated with a transient op, if any.
		Used by MainWindow so the TopBar pill can open the correct lab even
		while the lab is still starting/resetting (before running_lab_id exists).
		"""
		return self._runtime_op_lab_id

	def _refresh_progress_after_solve_async(self, lab_id: str) -> None:
		"""
		After a correct flag submission, the solve is recorded server-side via telemetry.
		That update can land slightly after we mark solved locally. To prevent the UI
		(Home page / tiles) from "flipping back" to unsolved, we force-refresh the
		API-backed progress map in the background until solved_at appears.
		"""
		lab_id = str(lab_id)

		def _bg():
			try:
				delay = 0.15
				attempts = 6
				for _ in range(attempts):
					try:
						pm = progress_db.get_progress_map(force=True)
						row = (pm or {}).get(lab_id, {}) or {}
						if row.get("solved_at"):
							# Replace AppState cache so all views read the updated state immediately.
							self._progress_cache = pm
							self._progress_dirty = False
							self._summary_dirty = True
							break
					except Exception:
						pass
					time.sleep(delay)
					delay = min(1.2, delay * 1.7)
			finally:
				# Always invalidate + signal UI refresh (best-effort).
				try:
					from PyQt5.QtCore import QTimer
					QTimer.singleShot(0, self._invalidate_all_progress_views)
				except Exception:
					try:
						self._invalidate_all_progress_views()
					except Exception:
						pass

		threading.Thread(target=_bg, daemon=True).start()

	# ---- Flag submission ----
	def submit_flag(self, lab_id: str, flag: str):
		lab_id = str(lab_id)
		submitted = (flag or "").strip()

		if not submitted:
			return (False, "Empty flag.", {})

		# Engagement: treat as started when user attempts a flag
		self.mark_started(lab_id)

		# Snapshot before submit so we can wait for labs_solved/xp to tick everywhere.
		prev_solved = 0
		try:
			prev_solved = int(progress_db.get_device_stats().labs_solved or 0)
		except Exception:
			prev_solved = 0

		# Server-side validation + solve materialization (only source of truth)
		ok, err, meta = progress_db.submit_flag(lab_id, submitted)
		if ok:
			# Force-refresh player stats so rank/XP updates everywhere.
			self._refresh_player_stats_async(expect_solved_increment=True, prev_labs_solved=prev_solved)

			# Force-refresh API-backed progress so Home/tiles don't show unsolved or flip back.
			self._refresh_progress_after_solve_async(lab_id)

			# refresh any UI that depends on solved state (lab list badges, etc.)
			self.labs_changed.emit()
			if self._selected and str(self._selected.id) == lab_id:
				self.selected_changed.emit(self._selected)

			return (True, "", meta)

		return (False, err or "Invalid flag.", meta or {})

	def check_flag(self, lab_id: str, flag: str):
		return self.submit_flag(lab_id, flag)

	# ---- Labs ----
	def refresh_labs(self) -> None:
		self._labs = discover_labs()
		if self._selected:
			self._selected = next((x for x in self._labs if x.id == self._selected.id), None)
		self.labs_changed.emit()

	def labs(self) -> List[Lab]:
		return list(self._labs)

	def filtered_labs(self) -> List[Lab]:
		q = (self._filter or "").strip().lower()
		if not q:
			return self.labs()
		out = []
		for lab in self._labs:
			hay = f"{lab.name} {lab.id} {lab.difficulty} {lab.description}".lower()
			if q in hay:
				out.append(lab)
		return out

	def set_filter(self, q: str) -> None:
		q = q or ""
		if q == self._filter:
			return
		self._filter = q
		self.filter_changed.emit(q)
		self.labs_changed.emit()

	def filter(self) -> str:
		return self._filter

	# ---- Selection ----
	def set_selected(self, lab: Optional[Lab]) -> None:
		if lab is self._selected or (lab and self._selected and lab.id == self._selected.id):
			return
		self._selected = lab
		self.selected_changed.emit(lab)

	def selected(self) -> Optional[Lab]:
		return self._selected

	# ---- Running lab ----
	def running(self) -> Optional[Lab]:
		if not self._running_lab_id:
			return None
		return next((x for x in self._labs if x.id == self._running_lab_id), None)

	def set_running_lab_id(self, lab_id: Optional[str]) -> None:
		if lab_id == self._running_lab_id:
			return
		self._running_lab_id = lab_id
		set_running_lab(lab_id)

		# IMPORTANT:
		# Do NOT clobber transient states (starting/stopping/resetting) in-flight.
		# Only resolve them to running/stopped when the runtime actually reaches that state.
		try:
			cur_op = (self._runtime_op or "").strip().lower()
			cur_lid = str(self._runtime_op_lab_id) if self._runtime_op_lab_id else ""
			new_lid = str(lab_id) if lab_id else ""

			if lab_id:
				# If we were starting/resetting this same lab, promote to RUNNING now.
				if cur_op in ("starting", "resetting") and (not cur_lid or cur_lid == new_lid):
					self.set_runtime_op("running", lab_id)
				# Otherwise, only set running if no transient op is active.
				elif cur_op not in ("starting", "stopping", "resetting"):
					self.set_runtime_op("running", lab_id)
			else:
				# If we were stopping/resetting, reaching None should become STOPPED.
				if cur_op in ("stopping", "resetting"):
					self.set_runtime_op("stopped", None)
				# Otherwise, only set stopped if no transient op is active.
				elif cur_op not in ("starting", "stopping", "resetting"):
					self.set_runtime_op("stopped", None)
		except Exception:
			pass

		# Treat "running" as "started" so Progress -> Active works even before any flag attempts.
		if lab_id:
			try:
				lab = next((x for x in self._labs if str(x.id) == str(lab_id)), None)
				diff = (getattr(lab, "difficulty", None) if lab else None)
				progress_db.mark_started(str(lab_id), difficulty=str(diff) if diff else None)
			except Exception:
				pass
			self._invalidate_all_progress_views()

		self.running_changed.emit(self.running())

	# ---- Docker status ----
	def refresh_docker(self) -> None:
		docker_ok, docker_msg = docker_available()
		compose_ok, compose_msg = compose_v2_available()

		if docker_ok and compose_ok:
			self._docker_text = f"Docker: {docker_msg} · Compose v2: {compose_msg}"
			self._docker_kind = "ok"

		elif docker_ok and not compose_ok:
			self._docker_text = f"Docker: {docker_msg} · Compose v2: Unavailable ({compose_msg})"
			self._docker_kind = "bad"

		else:
			# Docker itself unavailable; Compose status is secondary here
			self._docker_text = f"Docker: Unavailable ({docker_msg})"
			self._docker_kind = "bad"
		self.docker_changed.emit(self._docker_text, self._docker_kind)


	def _verify_runtime_running_lab(self) -> None:
		"""
		Prevent stale runtime state from blocking the UI.
		If runtime.json says a lab is running but Compose reports nothing running, clear it.
		"""
		if not self._running_lab_id:
			return

		docker_ok, _ = docker_available()
		compose_ok, _ = compose_v2_available()
		if not (docker_ok and compose_ok):
			# If Docker/Compose aren't available, don't mutate runtime state.
			return

		lab = next((x for x in self._labs if x.id == self._running_lab_id), None)
		if not lab:
			set_running_lab(None)
			self._running_lab_id = None
			self.running_changed.emit(None)
			return

		running, _details = compose_has_running(str(lab.path), lab.compose_file)
		if not running:
			set_running_lab(None)
			self._running_lab_id = None
			self.running_changed.emit(None)

	def docker_status(self):
		return self._docker_text, self._docker_kind

	# ---- Progress (ADDED) ----
	def progress_map(self) -> dict:
		"""
		{ lab_id: {started_at, solved_at, attempts} }
		"""
		if self._progress_cache is None or self._progress_dirty:
			self._progress_cache = progress_db.get_progress_map()
			self._progress_dirty = False
		return self._progress_cache

	def is_solved(self, lab_id: str) -> bool:
		row = self.progress_map().get(str(lab_id), {})
		return bool(row.get("solved_at"))

	def total_attempts(self) -> int:
		if self._summary_cache is None or self._summary_dirty:
			self._summary_cache = progress_db.get_summary()
			self._summary_dirty = False
		return int((self._summary_cache or {}).get("attempts", 0))

	def get_notes(self, lab_id: str) -> str:
		lab_id = str(lab_id)
		if lab_id not in self._notes_cache:
			self._notes_cache[lab_id] = progress_db.get_notes(lab_id)
		return self._notes_cache[lab_id]
 

	def set_notes(self, lab_id: str, notes: str) -> None:
		lab_id = str(lab_id)
		text = notes or ""
		progress_db.set_notes(lab_id, text)
		self._notes_cache[lab_id] = text
		# notes are part of "progress views" (detail page, home, etc.)
		self.progress_changed.emit()

	# Optional helpers (useful later)
	def mark_started(self, lab_id: str) -> None:
		lab = next((x for x in self._labs if str(x.id) == str(lab_id)), None)
		diff = (getattr(lab, "difficulty", None) if lab else None)
		progress_db.mark_started(str(lab_id), difficulty=str(diff) if diff else None)
		self._invalidate_all_progress_views()

	def mark_attempt(self, lab_id: str) -> None:
		progress_db.mark_attempt(str(lab_id))
		self._invalidate_all_progress_views()

	def mark_solved(self, lab_id: str) -> None:
		lab = next((x for x in self._labs if str(x.id) == str(lab_id)), None)
		diff = (getattr(lab, "difficulty", None) if lab else None)
		progress_db.mark_solved(str(lab_id), difficulty=str(diff) if diff else None)
		self._invalidate_all_progress_views()

	# ---- Logging ----
	def log(self, line: str) -> None:
		self.log_line.emit(line)
