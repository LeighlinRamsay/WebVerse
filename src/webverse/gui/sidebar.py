# gui/sidebar.py
from __future__ import annotations

import os
import threading

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QMessageBox, QSizePolicy
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QTimer

from webverse.gui.widgets.auth_dialog import LoginDialog, SignupDialog, try_device_login
from webverse.core import progress_db

_RANK_TIERS = [
	(0, "Recruit"),
	(500, "Operator"),
	(1500, "Specialist"),
	(3500, "Veteran"),
	(7000, "Elite"),
	(12000, "Legend"),
]

class _ClickableFrame(QFrame):
	def mousePressEvent(self, e):
		if hasattr(self, "_on_click") and callable(self._on_click):
			self._on_click()
		return super().mousePressEvent(e)


class _NavButton(QPushButton):
	def __init__(self, text: str):
		super().__init__(text)
		self.setObjectName("NavButton")
		self.setCursor(Qt.PointingHandCursor)
		self.setProperty("active", False)
		self.setProperty("locked", False)

	def set_active(self, active: bool):
		self.setProperty("active", active)
		self.style().unpolish(self)
		self.style().polish(self)
		self.update()

	def set_locked(self, locked: bool):
		self.setProperty("locked", bool(locked))
		self.style().unpolish(self)
		self.style().polish(self)
		self.update()


class Sidebar(QFrame):
	auth_changed = pyqtSignal()

	def __init__(self, stack, parent=None, profile_index: int = -1, show_learning: bool = True):
		super().__init__(parent)
		self.setObjectName("Sidebar")
		self.stack = stack

		self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
		self.setMinimumWidth(340)
		self.setMaximumWidth(340)

		self._settings = QSettings("WebVerse", "WebVerse")
		self._profile_index = profile_index
		self._show_learning = bool(show_learning)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(14, 14, 14, 14)
		layout.setSpacing(10)

		# Build nav dynamically so we can hide Learning cleanly.
		# Each item: (label, stack_index)
		self._nav_items = [
			("Home", 0),
			("Browse Labs", 1),
		]
		if self._show_learning:
			self._nav_items.append(("Learning", 2))
		self._nav_items += [
			("Progress", 4),
		]

		self.buttons = []
		self._page_for_button = []
		for (label, stack_idx) in self._nav_items:
			btn = _NavButton(label)
			btn.clicked.connect(lambda _=False, p=int(stack_idx): self.set_page(p))
			self.buttons.append(btn)
			self._page_for_button.append(int(stack_idx))
			layout.addWidget(btn)

		# Auth block (replaces Docker badge)
		self.auth_badge = QFrame()
		self.auth_badge.setObjectName("AuthBadge")

		self.auth_badge.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
		self.auth_badge.setFixedHeight(92)

		al = QHBoxLayout(self.auth_badge)
		al.setContentsMargins(10, 8, 10, 8)
		al.setSpacing(8)

		self.signup_btn = QPushButton("Signup")
		self.signup_btn.setObjectName("AuthBadgeBtn")
		self.signup_btn.setCursor(Qt.PointingHandCursor)

		self.login_btn = QPushButton("Login")
		self.login_btn.setObjectName("AuthBadgeBtn")
		self.login_btn.setCursor(Qt.PointingHandCursor)

		self.profile_badge = _ClickableFrame()
		self.profile_badge.setObjectName("ProfileBadge")
		self.profile_badge.setAttribute(Qt.WA_StyledBackground, True)

		self.profile_badge.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
		self.profile_badge.setFixedHeight(72)

		pl = QVBoxLayout(self.profile_badge)
		pl.setContentsMargins(12, 10, 12, 10)
		pl.setSpacing(6)

		top = QHBoxLayout()
		self.profile_title = QLabel("Profile")
		self.profile_title.setObjectName("ProfileTitle")
		self.profile_meta = QLabel("—")
		self.profile_meta.setObjectName("ProfileMeta")
		top.addWidget(self.profile_title, 1)
		top.addWidget(self.profile_meta, 0, Qt.AlignRight)
		pl.addLayout(top)

		self.profile_xp_bar = QFrame()
		self.profile_xp_bar.setObjectName("XPBar")
		
		self.profile_xp_bar.setFixedHeight(6)
		self.profile_xp_bar.setAttribute(Qt.WA_StyledBackground, True)
		self.profile_xp_bar.setProperty("xp_pct", 0.02)

		self.profile_xp_fill = QFrame(self.profile_xp_bar)
		self.profile_xp_fill.setObjectName("XPFill")
		self.profile_xp_fill.setAttribute(Qt.WA_StyledBackground, True)
		pl.addWidget(self.profile_xp_bar)

		self.profile_hint = QLabel("Click to view your stats →")
		self.profile_hint.setObjectName("ProfileHint")
		pl.addWidget(self.profile_hint)

		self.profile_badge._on_click = self._open_profile

		al.addWidget(self.signup_btn, 1)
		al.addWidget(self.login_btn, 1)
		al.addWidget(self.profile_badge, 2)

		layout.addStretch(1)
		layout.addSpacing(10)

		self.signup_btn.clicked.connect(self._open_signup)
		self.login_btn.clicked.connect(self._open_login)

		# Backwards-compat: keep a hidden docker badge object so any existing
		# code calling set_docker_status() won't crash.

		layout.addWidget(self.auth_badge, 0)

		self.docker_badge = QFrame()
		self.docker_badge.setObjectName("DockerBadge")
		self.docker_text = QLabel("Docker: —")
		self.docker_text.setObjectName("DockerBadgeText")

		# attempt device auto-login if no token yet (delay signal emit until event loop)
		_did_auto_login = False
		if not str(self._settings.value("auth/access_token", "") or "").strip():
			try:
				data = try_device_login(api_base_url=self._api_base_url())
				if isinstance(data, dict) and str(data.get("access_token") or "").strip():
					_did_auto_login = True
			except Exception:
				pass

		self._refresh_auth_ui()

		# Notify the rest of the app (Home/Profile/etc) that auth changed.
		# Use a singleShot so MainWindow has time to connect to this signal during startup.
		if _did_auto_login:
			try:
				QTimer.singleShot(0, self.auth_changed.emit)
			except Exception:
				pass

		# Apply lock AFTER auth UI is known (token/username may be filled by auto-login)
		self._apply_access_lock()

		# If a token exists but is stale, progress_db will clear it on 401 and
		# we should immediately flip UI back to Signup/Login.
		if str(self._settings.value("auth/access_token", "") or "").strip():
			self._refresh_profile_stats_async()

		self.set_page(0)

	# Public hook so ProfileView can force UI refresh after logout.
	def refresh_auth(self):
		self._refresh_auth_ui()
		self._apply_access_lock()
		self.refresh_mission_feed()

	def resizeEvent(self, event):
		super().resizeEvent(event)
		try:
			pct = float(self.profile_xp_bar.property("xp_pct") or 0.02)
		except Exception:
			pct = 0.02
		self._layout_profile_xp_fill(pct)

	def _layout_profile_xp_fill(self, pct: float):
		try:
			pct = max(0.02, min(1.0, float(pct)))
		except Exception:
			pct = 0.02

		try:
			bar_w = max(0, self.profile_xp_bar.width())
			bar_h = max(0, self.profile_xp_bar.height())
			fill_w = max(8, int(bar_w * pct))
			self.profile_xp_fill.setGeometry(0, 0, fill_w, bar_h)
		except Exception:
			pass

	def set_page(self, index: int):
		# If the device is linked to an account but the user is logged out, disable
		# certain pages (do NOT hard-block the entire GUI).

		if int(index) == 3:
			# Lab Detail should not light up any sidebar button, but it is still a valid page.
			self.stack.setCurrentIndex(index)
			return

		if self._is_access_locked_for_index(index):
			# Best-effort: nudge them to login instead of navigating.
			try:
				QMessageBox.information(self, "Login required", "Login to access this page.")
			except Exception:
				pass
			return

		# index is the STACK index (not the button index)
		self.stack.setCurrentIndex(index)

		# Active state: highlight the button whose stack index matches,
		# except Lab Detail (3) which should highlight none.
		for btn, (_label, stack_idx) in zip(self.buttons, self._nav_items):
			btn.set_active(int(index) != 3 and int(index) == int(stack_idx))

	def _device_is_linked(self) -> bool:
		"""
		Only apply access lock if this device is linked to an account.
		This allows fully-offline/guest usage when a device has never been linked.
		"""
		# 1) Prefer an explicit helper in progress_db if you have one.
		for fn_name in ("is_device_linked", "device_is_linked", "is_device_linked_to_account", "device_linked"):
			try:
				fn = getattr(progress_db, fn_name, None)
				if callable(fn):
					return bool(fn())
			except Exception:
				pass

		# 2) Fallback to persisted settings flags if present.
		try:
			v = self._settings.value("auth/device_linked", None)
			if v is not None:
				if isinstance(v, str):
					return v.strip().lower() in ("1", "true", "yes", "y", "on")
				return bool(v)
		except Exception:
			pass

		# 3) Last-resort heuristic: if we have ever had a username saved, we consider it linked.
		try:
			u = str(self._settings.value("auth/username", "") or "").strip()
			return bool(u)
		except Exception:
			return False

	def _is_logged_in(self) -> bool:
		# IMPORTANT: keep this aligned with MainWindow's lock rules (token-based).
		try:
			fn = getattr(progress_db, "is_logged_in", None)
			if callable(fn):
				return bool(fn())
		except Exception:
			pass
		try:
			token = str(self._settings.value("auth/access_token", "") or "").strip()
			return bool(token)
		except Exception:
			return False

	def _is_access_locked_for_index(self, stack_index: int) -> bool:
		# Lock only applies if device is linked AND user is logged out.
		if not self._device_is_linked():
			return False
		if self._is_logged_in():
			return False

		# Pages to disable when linked-but-logged-out:
		# - Browse (1), Lab Detail (3), Progress (4), Profile (profile_index)
		# Learning (2) stays accessible; Home (0) stays accessible.
		restricted = {1, 3, 4}
		if self._profile_index is not None and self._profile_index >= 0:
			restricted.add(int(self._profile_index))
		return int(stack_index) in restricted

	def _apply_access_lock(self) -> None:
		# Don’t assume a fixed number/order of buttons (Learning is optional).
		for btn, (_label, stack_idx) in zip(self.buttons, self._nav_items):
			try:
				is_locked = self._is_access_locked_for_index(int(stack_idx))
				btn.setEnabled(not is_locked)
				btn.set_locked(is_locked)
				btn.setToolTip("Locked — login required" if is_locked else "")
			except Exception:
				continue

		# Profile badge itself should only be clickable when logged in.
		try:
			locked = self._is_access_locked_for_index(self._profile_index)
			self.profile_badge.setEnabled((not locked) and self._is_logged_in())
			self.profile_badge.setProperty("locked", bool(locked))
			self.profile_badge.style().unpolish(self.profile_badge)
			self.profile_badge.style().polish(self.profile_badge)
			self.profile_badge.update()
		except Exception:
			pass

		try:
			self.profile_badge.setToolTip("Locked — login required" if locked else "")
		except Exception:
			pass

	def _api_base_url(self) -> str:
		# Prefer new env var; keep legacy var for backwards compat.
		return os.getenv(
			"WEBVERSE_API_BASE_URL",
			os.getenv("WEBVERSE_API_URL", "https://api-opensource.webverselabs.com"),
		).rstrip("/")

	def _refresh_auth_ui(self):
		token = str(self._settings.value("auth/access_token", "") or "").strip()
		username = str(self._settings.value("auth/username", "") or "").strip()
		rank = str(self._settings.value("auth/rank", "") or "").strip()
		xp = int(self._settings.value("auth/xp", 0) or 0)

		# Logged-in UI should require BOTH a token and username.
		# Token validity is enforced by progress_db: if /v1/auth/me returns 401,
		# it clears token/username and this becomes False.
		logged_in = bool(token and username)

		# Parent disable cascades. Always re-enable the whole block before toggling children.
		try:
			self.setEnabled(True)
			self.auth_badge.setEnabled(True)
		except Exception:
			pass

		# If anything previously disabled/locked this block, undo it here.
		# (Disabled state can persist even after setVisible(True).)
		try:
			self.auth_badge.setEnabled(True)
		except Exception:
			pass
		for w in (self.profile_badge, self.signup_btn, self.login_btn):
			try:
				w.setEnabled(True)
				# If you use a QSS rule like [locked="true"], make sure it's cleared.
				w.setProperty("locked", False)
				w.style().unpolish(w)
				w.style().polish(w)
				w.update()
			except Exception:
				pass

		self.signup_btn.setVisible(not logged_in)
		self.login_btn.setVisible(not logged_in)
		self.profile_badge.setVisible(logged_in)

		if logged_in:
			# HARD force: if we’re logged in, the badge must be clickable and non-grey.
			try:
				self.profile_badge.setEnabled(True)
				self.profile_badge.setProperty("locked", False)
				self.profile_badge.style().unpolish(self.profile_badge)
				self.profile_badge.style().polish(self.profile_badge)
				self.profile_badge.update()
			except Exception:
				pass

			label = f"{username}"
			if rank:
				label = f"{username} · {rank}"
			self.profile_title.setText(label)
			self.profile_meta.setText(f"{xp} XP")

			# Match ProfileView behavior:
			# fill is based on xp / next_rank_xp, not tier-relative progress
			next_rank_xp = None
			for threshold, _name in _RANK_TIERS:
				if xp < int(threshold):
					next_rank_xp = int(threshold)
					break

			if next_rank_xp is None:
				pct = 1.0
			else:
				pct = min(1.0, float(xp) / float(next_rank_xp))

			self.profile_xp_bar.setProperty("xp_pct", float(pct))
			QTimer.singleShot(0, lambda p=float(pct): self._layout_profile_xp_fill(p))

		# Always keep locks consistent with auth UI state (runs last)
		self._apply_access_lock()

		# Final safety: if we’re logged in, never leave it disabled OR locked-styled.
		if logged_in:
			try:
				self.profile_badge.setEnabled(True)
				self.profile_badge.setProperty("locked", False)  # must override any stale lock prop

				# Also ensure children don't inherit disabled state styling
				for w in (self.profile_title, self.profile_meta, self.profile_hint, self.profile_xp_bar, self.profile_xp_fill):
					try:
						w.setEnabled(True)
					except Exception:
						pass

				self.profile_badge.style().unpolish(self.profile_badge)
				self.profile_badge.style().polish(self.profile_badge)
				self.profile_badge.update()
			except Exception:
				pass

	def _refresh_profile_stats_async(self):
		# Best-effort cloud refresh; never blocks the UI.
		def _bg():
			try:
				progress_db.get_device_stats(force=True)
				from PyQt5.QtCore import QTimer
				QTimer.singleShot(0, self._refresh_auth_ui)
			except Exception:
				pass

		threading.Thread(target=_bg, daemon=True).start()

	def _open_signup(self):
		dlg = SignupDialog(api_base_url=self._api_base_url(), parent=self)
		if dlg.exec_() == dlg.Accepted:
			QMessageBox.information(self, "Signup", "Signup successful. You're logged in.")
			self._refresh_profile_stats_async()
			self._refresh_auth_ui()

			try:
				self.auth_changed.emit()
			except Exception:
				pass

	def _open_login(self):
		dlg = LoginDialog(api_base_url=self._api_base_url(), parent=self)
		if dlg.exec_() == dlg.Accepted:
			QMessageBox.information(self, "Login", "Login successful.")
			self._refresh_profile_stats_async()
			self._refresh_auth_ui()

			try:
				self.auth_changed.emit()
			except Exception:
				pass

	def _open_profile(self):
		# Respect lock rules (linked device but logged out)
		if self._is_access_locked_for_index(self._profile_index):
			self._open_login()
			return

		if self._profile_index is not None and self._profile_index >= 0:
			# Always re-activate profile (fast refresh) on every click.
			try:
				w = self.stack.widget(self._profile_index)
				if hasattr(w, "on_activated"):
					w.on_activated()
			except Exception:
				pass
			self.set_page(self._profile_index)

	def set_docker_status(self, text: str, kind: str = "neutral"):
		# Docker badge is no longer shown; surface status as a tooltip on the auth block.
		if hasattr(self, "auth_badge") and self.auth_badge is not None:
			self.auth_badge.setToolTip(text)
			self.signup_btn.setToolTip(text)
			self.login_btn.setToolTip(text)

		palette = {
			"ok": ("rgba(34,197,94,0.14)", "rgba(34,197,94,0.30)"),
			"warn": ("rgba(245,158,11,0.14)", "rgba(245,158,11,0.30)"),
			"bad": ("rgba(239,68,68,0.14)", "rgba(239,68,68,0.30)"),
			"neutral": ("rgba(16,20,28,0.55)", "rgba(255,255,255,0.08)"),
		}
		
		bg, bd = palette.get(kind, palette["neutral"])
		if getattr(self, "docker_badge", None) is not None:
			self.docker_badge.setStyleSheet(
				f"QFrame#DockerBadge {{ background: {bg}; border: 1px solid {bd}; }}"
			)
		if getattr(self, "docker_text", None) is not None:
			self.docker_text.setText(text)
