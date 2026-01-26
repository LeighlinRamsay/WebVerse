# gui/app_state.py
from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from core.registry import discover_labs
from core.runtime import get_running_lab, set_running_lab
from core.docker_ops import docker_available, compose_v2_available, compose_has_running
from core.models import Lab

from core import progress_db


class AppState(QObject):
    labs_changed = pyqtSignal()
    filter_changed = pyqtSignal(str)
    selected_changed = pyqtSignal(object)  # Lab|None
    running_changed = pyqtSignal(object)   # Lab|None
    docker_changed = pyqtSignal(str, str)  # text, kind
    log_line = pyqtSignal(str)
    progress_changed = pyqtSignal()        # progress/notes updated (refresh badges, stats, etc.)

    def __init__(self):
        super().__init__()
        self._labs: List[Lab] = []
        self._filter: str = ""
        self._selected: Optional[Lab] = None
        self._running_lab_id: Optional[str] = get_running_lab()
        self._docker_text: str = "Docker: Unknown"
        self._docker_kind: str = "neutral"

        # ---- Progress/Notes caches (avoid repeated SQLite reads) ----
        self._progress_cache: Optional[Dict[str, dict]] = None
        self._progress_dirty: bool = True
        self._summary_cache: Optional[dict] = None
        self._summary_dirty: bool = True
        self._notes_cache: Dict[str, str] = {}

        self.refresh_labs()
        self.refresh_docker()
        self._verify_runtime_running_lab()

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

    # ---- Flag submission ----
    def submit_flag(self, lab_id: str, flag: str):
        lab_id = str(lab_id)
        submitted = (flag or "").strip()

        if not submitted:
            self.mark_attempt(lab_id)
            return (False, "Empty flag.")

        # count progress
        self.mark_started(lab_id)
        self.mark_attempt(lab_id)

        # find lab
        lab = next((x for x in self._labs if str(x.id) == lab_id), None)
        if not lab:
            return (False, "Lab not found.")

        expected_sha = getattr(lab, "flag_sha256", None) or getattr(lab, "flagSha256", None) or ""
        expected_sha = (expected_sha or "").strip().lower()

        if not expected_sha:
            return (False, "This lab has no flag_sha256 configured.")

        # validate
        got_sha = hashlib.sha256(submitted.encode("utf-8")).hexdigest()
        ok = (got_sha == expected_sha)

        if ok:
            # mark solved (only sets solved_at if not already set)
            self.mark_solved(lab_id)

            # refresh any UI that depends on solved state (lab list badges, etc.)
            self.labs_changed.emit()
            if self._selected and str(self._selected.id) == lab_id:
                self.selected_changed.emit(self._selected)

            return (True, "")

        return (False, "")

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

        # Treat "running" as "started" so Progress -> Active works even before any flag attempts.
        if lab_id:
            try:
                progress_db.mark_started(str(lab_id))
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
        progress_db.mark_started(str(lab_id))
        self._invalidate_all_progress_views()

    def mark_attempt(self, lab_id: str) -> None:
        progress_db.mark_attempt(str(lab_id))
        self._invalidate_all_progress_views()

    def mark_solved(self, lab_id: str) -> None:
        progress_db.mark_solved(str(lab_id))
        self._invalidate_all_progress_views()

    # ---- Logging ----
    def log(self, line: str) -> None:
        self.log_line.emit(line)
