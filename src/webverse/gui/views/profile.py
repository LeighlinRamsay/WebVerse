from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, pyqtSlot
from PyQt5.QtWidgets import (
	QWidget,
	QVBoxLayout,
	QHBoxLayout,
	QFrame,
	QLabel,
	QScrollArea,
	QSpacerItem,
	QSizePolicy,
)

from webverse.core import progress_db
from webverse.core.registry import discover_labs


@dataclass
class _ActivityItem:
	type: str
	lab_id: str | None
	xp_delta: int
	timestamp: int

class _LogoutWorker(QObject):
	"""
	Background cache purge so logout never blocks the UI.
	Best-effort: never raises.
	"""
	finished = pyqtSignal()

	@pyqtSlot()
	def run(self):
		try:
			s = progress_db._settings()  # internal but stable across app

			# Always remove auth keys (safe even if missing)
			for k in (
				"auth/access_token",
				"auth/email",
				"auth/username",
				"auth/rank",
				"auth/xp",
			):
				try:
					s.remove(k)
				except Exception:
					pass

			# Best-effort server logout (token_version bump)
			try:
				progress_db.logout_remote_best_effort()
			except Exception:
				pass

			# Purge likely cache namespaces (rank/xp/profile/activity/progress/etc.)
			try:
				keys = list(s.allKeys())
			except Exception:
				keys = []

			prefixes = (
				"auth/",
				"profile/",
				"me/",
				"user/",
				"rank/",
				"xp/",
				"activity/",
				"labs/",
				"progress/",
				"cache/",
			)

			for key in keys:
				try:
					if key.startswith(prefixes):
						s.remove(key)
				except Exception:
					pass

			try:
				s.sync()
			except Exception:
				pass

			# Clear any module-level caches if present
			for fn_name in (
				"invalidate_remote_cache",
				"clear_cache",
				"clear_local_cache",
				"reset_local_progress",
			):
				try:
					fn = getattr(progress_db, fn_name, None)
					if callable(fn):
						fn()
				except Exception:
					pass

		except Exception:
			pass
		finally:
			# Hard purge: clear everything local on logout (QSettings + in-memory caches)
			try:
				progress_db.clear_everything_on_logout()
			except Exception:
				pass
			self.finished.emit()

class _ProfileFetchWorker(QObject):
	"""Fetch profile data off the UI thread."""
	success = pyqtSignal(int, dict)      # req_id, data
	auth_required = pyqtSignal(int)      # req_id
	failed = pyqtSignal(int, str)        # req_id, message
	finished = pyqtSignal(int)           # req_id

	def __init__(self, *, req_id: int, force: bool, retries: int):
		super().__init__()
		self.req_id = int(req_id)
		self.force = bool(force)
		self.retries = int(retries)

	@pyqtSlot()
	def run(self):
		try:
			data = progress_db.fetch_profile(force=self.force, retries=self.retries)
			self.success.emit(self.req_id, data or {})
		except progress_db.AuthRequiredError:
			self.auth_required.emit(self.req_id)
		except Exception as e:
			self.failed.emit(self.req_id, str(e) or "profile fetch failed")
		finally:
			self.finished.emit(self.req_id)


class _ActivityFetchWorker(QObject):
	"""Fetch a page of activity off the UI thread."""
	success = pyqtSignal(int, dict)      # req_id, page
	auth_required = pyqtSignal(int)      # req_id
	failed = pyqtSignal(int, str)        # req_id, message
	finished = pyqtSignal(int)           # req_id

	def __init__(self, *, req_id: int, cursor: Optional[int], limit: int, retries: int):
		super().__init__()
		self.req_id = int(req_id)
		self.cursor = int(cursor) if cursor is not None else None
		self.limit = int(limit)
		self.retries = int(retries)

	@pyqtSlot()
	def run(self):
		try:
			page = progress_db.fetch_activity_me_page(cursor=self.cursor, limit=self.limit, retries=self.retries)
			self.success.emit(self.req_id, page or {})
		except progress_db.AuthRequiredError:
			self.auth_required.emit(self.req_id)
		except Exception as e:
			self.failed.emit(self.req_id, str(e) or "activity fetch failed")
		finally:
			self.finished.emit(self.req_id)

class _XPBar(QFrame):
	def __init__(self):
		super().__init__()
		self.setObjectName("ProfileXPBar")
		self.setFixedHeight(14)
		self._fill = QFrame(self)
		self._fill.setObjectName("ProfileXPFill")
		self._fill.setGeometry(0, 0, 0, 14)
		self._pct = 0.0

	def set_progress(self, pct: float):
		try:
			pct = float(pct)
		except Exception:
			pct = 0.0
		self._pct = max(0.0, min(1.0, pct))
		self._relayout()

	def resizeEvent(self, e):
		super().resizeEvent(e)
		self._relayout()

	def _relayout(self):
		w = max(0, int(self.width() * self._pct))
		self._fill.setGeometry(0, 0, w, self.height())


class _KPI(QFrame):
	def __init__(self, title: str):
		super().__init__()
		self.setObjectName("ProfileKPI")
		v = QVBoxLayout(self)
		v.setContentsMargins(14, 12, 14, 12)
		v.setSpacing(2)

		self.value = QLabel("—")
		self.value.setObjectName("KPIValue")
		self.label = QLabel(title)
		self.label.setObjectName("KPILabel")
		v.addWidget(self.value)
		v.addWidget(self.label)

	def set_value(self, text: str):
		self.value.setText(text)


class _ActivityRow(QFrame):
	def __init__(self, *, icon_path: Optional[str], text: str, xp_text: str, ts_text: str):
		super().__init__()
		self.setObjectName("ActivityRow")
		self.setProperty("variant", "")

		root = QHBoxLayout(self)
		root.setContentsMargins(12, 10, 12, 10)
		root.setSpacing(12)

		self.icon = QLabel()
		self.icon.setObjectName("ActivityIcon")
		self.icon.setFixedSize(44, 44)
		self.icon.setAlignment(Qt.AlignCenter)
		if icon_path and os.path.exists(icon_path):
			from PyQt5.QtGui import QPixmap
			pm = QPixmap(icon_path)
			if not pm.isNull():
				pm = pm.scaled(44, 44, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
				self.icon.setPixmap(pm)
		root.addWidget(self.icon)

		mid = QVBoxLayout()
		mid.setSpacing(1)
		root.addLayout(mid, 1)

		self.text = QLabel(text)
		self.text.setObjectName("ActivityText")
		mid.addWidget(self.text)

		self.meta = QLabel(ts_text)
		self.meta.setObjectName("ActivityMeta")
		mid.addWidget(self.meta)

		self.xp = QLabel(xp_text)
		self.xp.setObjectName("ActivityXP")
		self.xp.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
		root.addWidget(self.xp)

class _LogoutButton(QFrame):
	"""
	Custom "ghost action" button (Option A):
	- Not a QPushButton
	- Own hover/pressed handling (QSS driven via dynamic properties)
	- Icon + label layout
	"""
	clicked = pyqtSignal()

	def __init__(self, text: str = "Logout", parent: Optional[QWidget] = None):
		super().__init__(parent)
		self.setObjectName("ProfileLogoutBtn")
		self.setAttribute(Qt.WA_StyledBackground, True)
		self.setCursor(Qt.PointingHandCursor)
		self.setFocusPolicy(Qt.NoFocus)
		self.setMouseTracking(True)
		self.setProperty("hover", False)
		self.setProperty("pressed", False)

		lay = QHBoxLayout(self)
		lay.setContentsMargins(14, 8, 12, 8)
		lay.setSpacing(8)

		self._icon = QLabel("⎋")
		self._icon.setObjectName("ProfileLogoutBtnIcon")
		self._icon.setAlignment(Qt.AlignCenter)
		self._icon.setFixedWidth(16)
		lay.addWidget(self._icon, 0)

		self._text = QLabel(text)
		self._text.setObjectName("ProfileLogoutBtnText")
		self._text.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
		lay.addWidget(self._text, 1)

		self.setFixedHeight(36)
		self.setMinimumWidth(120)

	def setText(self, text: str):
		self._text.setText(text)

	def _set_state(self, *, hover: Optional[bool] = None, pressed: Optional[bool] = None):
		changed = False
		if hover is not None:
			if bool(self.property("hover")) != bool(hover):
				self.setProperty("hover", bool(hover))
				changed = True
		if pressed is not None:
			if bool(self.property("pressed")) != bool(pressed):
				self.setProperty("pressed", bool(pressed))
				changed = True
		if changed:
			try:
				self.style().unpolish(self)
				self.style().polish(self)
			except Exception:
				pass
			self.update()

	def enterEvent(self, e):
		super().enterEvent(e)
		if self.isEnabled():
			self._set_state(hover=True)

	def leaveEvent(self, e):
		super().leaveEvent(e)
		self._set_state(hover=False, pressed=False)

	def mousePressEvent(self, e):
		if not self.isEnabled():
			return super().mousePressEvent(e)
		if e.button() == Qt.LeftButton:
			self._set_state(pressed=True)
			e.accept()
			return
		return super().mousePressEvent(e)

	def mouseReleaseEvent(self, e):
		if not self.isEnabled():
			return super().mouseReleaseEvent(e)
		was_pressed = bool(self.property("pressed"))
		self._set_state(pressed=False)
		if was_pressed and e.button() == Qt.LeftButton:
			if self.rect().contains(e.pos()):
				self.clicked.emit()
				e.accept()
				return
		return super().mouseReleaseEvent(e)

	def setEnabled(self, enabled: bool):
		super().setEnabled(enabled)
		if not enabled:
			self._set_state(hover=False, pressed=False)


class ProfileView(QWidget):
	"""Mission-control style profile with auto-refresh + infinite activity."""

	auth_changed = pyqtSignal()
	toast_requested = pyqtSignal(str, str, str)  # title, body, variant

	def __init__(self, api_base_url: str):
		super().__init__()
		self.api_base_url = (api_base_url or "").rstrip("/")
		self.setObjectName("ProfileRoot")
		self.setAttribute(Qt.WA_StyledBackground, True)

		# Lab lookup for icons (local install + user labs)
		self._labs_by_id = {str(x.id): x for x in discover_labs()}

		self._loading_profile = False
		self._loading_activity = False
		self._activity_next_cursor: Optional[int] = None
		self._activity_exhausted = False

		# ---- Throttling / coalescing ----
		self._last_activated_at = 0.0
		self._last_profile_applied_at = 0.0
		self._last_activity_applied_at = 0.0
		self._profile_refresh_ttl_s = 6.0
		self._activity_refresh_ttl_s = 10.0

		# ---- Async fetch plumbing ----
		self._profile_req_id = 0
		self._activity_req_id = 0
		self._profile_thread: Optional[QThread] = None
		self._profile_worker: Optional[_ProfileFetchWorker] = None
		self._activity_thread: Optional[QThread] = None
		self._activity_worker: Optional[_ActivityFetchWorker] = None

		root = QVBoxLayout(self)
		root.setContentsMargins(0, 0, 0, 0)
		root.setSpacing(0)

		self.scroll = QScrollArea()
		self.scroll.setObjectName("ProfileScroll")
		self.scroll.setWidgetResizable(True)
		self.scroll.setFrameShape(QFrame.NoFrame)
		root.addWidget(self.scroll)

		self.content = QWidget()
		self.content.setObjectName("ProfileContent")
		self.scroll.setWidget(self.content)

		cv = QVBoxLayout(self.content)
		cv.setContentsMargins(14, 14, 14, 18)
		cv.setSpacing(12)

		# --- Hero ---
		self.hero = QFrame()
		self.hero.setObjectName("ProfileHero")
		h = QVBoxLayout(self.hero)
		h.setContentsMargins(18, 16, 18, 16)
		h.setSpacing(10)

		top = QHBoxLayout()
		top.setSpacing(12)
		h.addLayout(top)

		self.avatar = QLabel("WV")
		self.avatar.setObjectName("ProfileAvatar")
		self.avatar.setFixedSize(58, 58)
		self.avatar.setAlignment(Qt.AlignCenter)
		top.addWidget(self.avatar)

		namecol = QVBoxLayout()
		namecol.setSpacing(2)
		top.addLayout(namecol, 1)

		self.username = QLabel("—")
		self.username.setObjectName("ProfileUsername")
		namecol.addWidget(self.username)

		self.rankline = QLabel("Rank • —")
		self.rankline.setObjectName("ProfileRankLine")
		namecol.addWidget(self.rankline)

		self.nextline = QLabel("Next Rank: —")
		self.nextline.setObjectName("ProfileNextLine")
		namecol.addWidget(self.nextline)

		self.btn_logout = _LogoutButton("Logout")
		self.btn_logout.clicked.connect(self._logout)

		top.addWidget(self.btn_logout)

		self.xpbar = _XPBar()
		h.addWidget(self.xpbar)

		self.xpmeta = QLabel("—")
		self.xpmeta.setObjectName("ProfileXPText")
		h.addWidget(self.xpmeta)

		cv.addWidget(self.hero)

		# --- KPIs ---
		row = QHBoxLayout()
		row.setSpacing(12)
		self.kpi_solved = _KPI("Labs solved")
		self.kpi_streak = _KPI("Streak days")
		self.kpi_total_xp = _KPI("Total XP")
		row.addWidget(self.kpi_solved)
		row.addWidget(self.kpi_streak)
		row.addWidget(self.kpi_total_xp)
		cv.addLayout(row)

		# --- Activity ---
		self.activity_panel = QFrame()
		self.activity_panel.setObjectName("ActivityPanel")
		ap = QVBoxLayout(self.activity_panel)
		ap.setContentsMargins(16, 14, 16, 14)
		ap.setSpacing(10)

		hdr = QHBoxLayout()
		hdr.setSpacing(8)
		ap.addLayout(hdr)
		self.activity_title = QLabel("Activity")
		self.activity_title.setObjectName("ActivityTitle")
		hdr.addWidget(self.activity_title)
		hdr.addStretch(1)
		self.activity_hint = QLabel("All-time")
		self.activity_hint.setObjectName("ActivityHint")
		hdr.addWidget(self.activity_hint)

		self.activity_list = QWidget()
		self.activity_list.setObjectName("ActivityList")
		self.activity_v = QVBoxLayout(self.activity_list)
		self.activity_v.setContentsMargins(0, 0, 0, 0)
		self.activity_v.setSpacing(10)
		ap.addWidget(self.activity_list)

		self.activity_loading = QLabel("Loading activity…")
		self.activity_loading.setObjectName("ActivityLoading")
		self.activity_loading.setAlignment(Qt.AlignCenter)
		ap.addWidget(self.activity_loading)

		cv.addWidget(self.activity_panel)

		# --- Member since ---
		self.member_since = QLabel("")
		self.member_since.setObjectName("MemberSince")
		self.member_since.setAlignment(Qt.AlignCenter)
		cv.addWidget(self.member_since)

		cv.addItem(QSpacerItem(10, 16, QSizePolicy.Minimum, QSizePolicy.Expanding))

		# Infinite-scroll trigger
		try:
			self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
		except Exception:
			pass

	def showEvent(self, e):
		super().showEvent(e)
		# Fetch immediately when the view becomes visible.
		QTimer.singleShot(0, lambda: self.on_activated())

	def on_activated(self):
		"""Called whenever the Profile nav is clicked / view is activated."""

		# Throttle repeated clicks (prevents UI churn + request storms)
		now = time.monotonic()
		if (now - float(self._last_activated_at or 0.0)) < 0.6:
			return
		self._last_activated_at = now

		if not progress_db.is_logged_in():
			# Hard-block: profile is not accessible when logged out.
			self._reset_ui_logged_out()
			self.toast_requested.emit("Login required", "Login to view your profile.", "warn")
			return

		# Only refresh if data is stale (keeps repeated clicks snappy)
		need_profile = (now - float(self._last_profile_applied_at or 0.0)) > float(self._profile_refresh_ttl_s)
		need_activity = (now - float(self._last_activity_applied_at or 0.0)) > float(self._activity_refresh_ttl_s)
		# Always fetch at least once.
		if self._last_profile_applied_at <= 0.0:
			need_profile = True
		if self._last_activity_applied_at <= 0.0:
			need_activity = True

		if need_profile:
			self._fetch_profile_async(force=True)

		# Activity pages are expensive to rebuild (lots of widgets). Only reset when stale.
		if need_activity:
			self._reset_activity()
			self._fetch_activity_next_async()

	def _reset_ui_logged_out(self):
		self.username.setText("—")
		self.rankline.setText("Rank • —")
		self.nextline.setText("Next Rank: —")
		self.xpbar.set_progress(0.0)
		self.xpmeta.setText("—")
		self.kpi_solved.set_value("—")
		self.kpi_streak.set_value("—")
		self.kpi_total_xp.set_value("—")
		self.member_since.setText("")
		self.btn_logout.setEnabled(False)
		self._clear_activity_rows()
		self.activity_loading.setText("Login to see your activity.")
		self.activity_loading.show()

	def _fetch_profile_async(self, *, force: bool):
		"""Async profile fetch (never blocks UI)."""
		if self._loading_profile:
			return
		self._loading_profile = True
		self.btn_logout.setEnabled(True)

		self._profile_req_id += 1
		req_id = int(self._profile_req_id)

		self._profile_thread = QThread(self)
		self._profile_worker = _ProfileFetchWorker(req_id=req_id, force=force, retries=3)
		self._profile_worker.moveToThread(self._profile_thread)

		self._profile_thread.started.connect(self._profile_worker.run)
		self._profile_worker.success.connect(self._on_profile_success)
		self._profile_worker.auth_required.connect(self._on_profile_auth_required)
		self._profile_worker.failed.connect(self._on_profile_failed)
		self._profile_worker.finished.connect(self._on_profile_finished)
		self._profile_worker.finished.connect(self._profile_thread.quit)
		self._profile_worker.finished.connect(self._profile_worker.deleteLater)
		self._profile_thread.finished.connect(self._profile_thread.deleteLater)
		self._profile_thread.start()

	@pyqtSlot(int, dict)
	def _on_profile_success(self, req_id: int, data: dict):
		# Ignore stale completions
		if int(req_id) != int(self._profile_req_id):
			return

		try:
			self._apply_profile(data or {})
			self._last_profile_applied_at = time.monotonic()

		except Exception:
			pass

	@pyqtSlot(int)
	def _on_profile_auth_required(self, req_id: int):
		if int(req_id) != int(self._profile_req_id):
			return
		self._reset_ui_logged_out()

	@pyqtSlot(int, str)
	def _on_profile_failed(self, req_id: int, msg: str):
		if int(req_id) != int(self._profile_req_id):
			return
		self.toast_requested.emit("Sync failed", "Couldn’t sync your profile.", "warn")

	@pyqtSlot(int)
	def _on_profile_finished(self, req_id: int):
		if int(req_id) != int(self._profile_req_id):
			return
		self._loading_profile = False

	def _apply_profile(self, data: Dict[str, Any]):
		username = str(data.get("username") or "").strip() or "—"
		rank = str(data.get("rank") or "Recruit")
		xp = int(data.get("xp") or 0)
		next_rank = str(data.get("next_rank") or "")
		next_rank_xp = int(data.get("next_rank_xp") or 0)
		labs_solved = int(data.get("labs_solved") or 0)
		streak_days = int(data.get("streak_days") or 0)
		created_at = str(data.get("created_at") or "").strip()

		# Avatar initials
		initials = "WV"
		if username and username != "—":
			parts = [p for p in username.replace("_", " ").split() if p]
			if len(parts) == 1:
				initials = parts[0][:2].upper()
			elif len(parts) >= 2:
				initials = (parts[0][:1] + parts[1][:1]).upper()
		self.avatar.setText(initials)

		self.username.setText(username)
		self.rankline.setText(f"{rank}  •  {xp:,} XP")

		# Progress to next rank
		if next_rank and next_rank_xp:
			remaining = max(0, int(next_rank_xp) - int(xp))
			self.nextline.setText(f"Next Rank: {next_rank}  •  {remaining:,} XP to go")
			pct = min(1.0, float(xp) / float(next_rank_xp)) if next_rank_xp > 0 else 0.0
			self.xpbar.set_progress(pct)
			self.xpmeta.setText(f"{xp:,} / {next_rank_xp:,}")
		else:
			self.nextline.setText("Next Rank: —")
			self.xpbar.set_progress(0.0)
			self.xpmeta.setText(f"{xp:,} XP")

		self.kpi_solved.set_value(str(labs_solved))
		self.kpi_streak.set_value(str(streak_days))
		self.kpi_total_xp.set_value(f"{xp:,}")

		if created_at:
			self.member_since.setText(f"Member since {created_at}")
		else:
			self.member_since.setText("")

	def _reset_activity(self):
		self._activity_next_cursor = None
		self._activity_exhausted = False
		self._clear_activity_rows()
		self.activity_loading.setText("Loading activity…")
		self.activity_loading.show()

	def _clear_activity_rows(self):
		while self.activity_v.count():
			item = self.activity_v.takeAt(0)
			w = item.widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()


	def _fetch_activity_next_async(self):
		"""Async activity paging (never blocks UI)."""
		if self._loading_activity or self._activity_exhausted:
			return
		self._loading_activity = True

		self._activity_req_id += 1
		req_id = int(self._activity_req_id)

		try:
			self.activity_loading.setText("Loading activity…")
			self.activity_loading.show()
		except Exception:
			pass

		self._activity_thread = QThread(self)
		self._activity_worker = _ActivityFetchWorker(req_id=req_id, cursor=self._activity_next_cursor, limit=25, retries=3)
		self._activity_worker.moveToThread(self._activity_thread)

		self._activity_thread.started.connect(self._activity_worker.run)
		self._activity_worker.success.connect(self._on_activity_success)
		self._activity_worker.auth_required.connect(self._on_activity_auth_required)
		self._activity_worker.failed.connect(self._on_activity_failed)
		self._activity_worker.finished.connect(self._on_activity_finished)
		self._activity_worker.finished.connect(self._activity_thread.quit)
		self._activity_worker.finished.connect(self._activity_worker.deleteLater)
		self._activity_thread.finished.connect(self._activity_thread.deleteLater)
		self._activity_thread.start()

	@pyqtSlot(int, dict)
	def _on_activity_success(self, req_id: int, page: dict):
		if int(req_id) != int(self._activity_req_id):
			return

		try:
			items = (page or {}).get("items") or []
			next_cursor = (page or {}).get("next_cursor")
			if not items:
				self._activity_exhausted = True
				if self.activity_v.count() == 0:
					self.activity_loading.setText("No activity yet.")
					self.activity_loading.show()
				else:
					self.activity_loading.hide()
				return

			for it in items:
				try:
					item = _ActivityItem(
						type=str(it.get("type") or ""),
						lab_id=str(it.get("lab_id")) if it.get("lab_id") else None,
						xp_delta=int(it.get("xp_delta") or 0),
						timestamp=int(it.get("timestamp") or 0),
					)
				except Exception:
					continue
				self._append_activity_row(item)

			self._activity_next_cursor = int(next_cursor) if next_cursor is not None else None
			self.activity_loading.hide()
			if self._activity_next_cursor is None:
				self._activity_exhausted = True
			self._last_activity_applied_at = time.monotonic()

		except Exception:
			self.toast_requested.emit("Sync failed", "Couldn’t sync activity history.", "warn")
			self._activity_exhausted = True
			self.activity_loading.setText("Couldn’t load activity.")
			self.activity_loading.show()
	
	@pyqtSlot(int)
	def _on_activity_auth_required(self, req_id: int):
		if int(req_id) != int(self._activity_req_id):
			return
		self._activity_exhausted = True
		self.activity_loading.setText("Login to see your activity.")
		self.activity_loading.show()

	@pyqtSlot(int, str)
	def _on_activity_failed(self, req_id: int, msg: str):
		if int(req_id) != int(self._activity_req_id):
			return
		self.toast_requested.emit("Sync failed", "Couldn’t sync activity history.", "warn")
		self._activity_exhausted = True
		self.activity_loading.setText("Couldn’t load activity.")
		self.activity_loading.show()

	@pyqtSlot(int)
	def _on_activity_finished(self, req_id: int):
		if int(req_id) != int(self._activity_req_id):
			return
		self._loading_activity = False

	def _append_activity_row(self, item: _ActivityItem):
		lab_name = item.lab_id or "Unknown"
		icon_path = None
		if item.lab_id and item.lab_id in self._labs_by_id:
			lab = self._labs_by_id[item.lab_id]
			img = str(getattr(lab, "image", "") or "").strip()
			if img:
				p = str(getattr(lab, "path", ""))
				candidate = os.path.join(p, img)
				if os.path.exists(candidate):
					icon_path = candidate
			lab_name = str(getattr(lab, "name", item.lab_id))

		verb = "Activity"
		if item.type == "lab_started":
			verb = "Started"
		elif item.type == "lab_solved":
			verb = "Solved"

		text = f"{verb} {lab_name}"
		xp_text = f"+{item.xp_delta} XP" if item.xp_delta else ""

		from datetime import datetime, timezone
		try:
			dt = datetime.fromtimestamp(int(item.timestamp), tz=timezone.utc)
			ts_text = dt.strftime("%b %d, %Y • %I:%M%p").replace(" 0", " ")
		except Exception:
			ts_text = ""

		r = _ActivityRow(icon_path=icon_path, text=text, xp_text=xp_text, ts_text=ts_text)
		self.activity_v.addWidget(r)

	def _on_scroll(self, value: int):
		try:
			bar = self.scroll.verticalScrollBar()
			if self._activity_exhausted or self._loading_activity:
				return
			# Load when within ~200px of bottom
			if value >= (bar.maximum() - 220):
				self._fetch_activity_next_async()
		except Exception:
			pass
	
	def _logout(self):
		# Fast-path: immediately invalidate token so UI flips to logged-out instantly.
		# Do NOT block the UI doing full cache purge.
		try:
			s = progress_db._settings()
			try:
				s.remove("auth/access_token")
			except Exception:
				pass
			try:
				s.sync()
			except Exception:
				pass
		except Exception:
			pass
		self.auth_changed.emit()
		self.toast_requested.emit("Logged out", "You’ve been logged out.", "info")
		self._reset_ui_logged_out()

		# Background cleanup: clear cached profile/rank/xp/activity/progress/etc.
		try:
			# Avoid stacking multiple workers if user clicks twice
			if getattr(self, "_logout_thread", None) is not None:
				try:
					if self._logout_thread.isRunning():
						return
				except Exception:
					pass

			self._logout_thread = QThread(self)
			self._logout_worker = _LogoutWorker()
			self._logout_worker.moveToThread(self._logout_thread)

			self._logout_thread.started.connect(self._logout_worker.run)
			self._logout_worker.finished.connect(self._logout_thread.quit)
			self._logout_worker.finished.connect(self._logout_worker.deleteLater)
			self._logout_thread.finished.connect(self._logout_thread.deleteLater)

			self._logout_thread.start()
		except Exception:
			pass
