# gui/main_window.py
from __future__ import annotations

import os
from pathlib import Path

from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame, QShortcut, QSizePolicy, QLayout, QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox
from PyQt5.QtCore import QTimer, Qt, QSize, QEvent, QUrl, QSettings
from PyQt5.QtGui import QKeySequence, QIcon, QDesktopServices

from webverse.gui.theme import qss_onyx_amber
from webverse.gui.widgets.topbar import TopBar
from webverse.gui.widgets.command_palette import CommandPalette

from webverse.gui.sidebar import Sidebar
from webverse.gui.widgets.toast import ToastHost

from webverse.core.updater import UpdateManager

from webverse.gui.views.home import HomeView
from webverse.gui.views.labs_browse import LabsBrowseView
from webverse.gui.views.lab_detail import LabDetailView
from webverse.gui.views.progress import ProgressView
from webverse.gui.views.settings import SettingsView
from webverse.gui.views.profile import ProfileView
from webverse.gui.widgets.solve_celebration import SolveCelebrationHost


class MainWindow(QMainWindow):
	def __init__(self, state):
		super().__init__()
		self.state = state

		self.setWindowTitle("WebVerse")
		self._settings = QSettings("WebVerse", "WebVerse")

		icon_path = Path(__file__).resolve().parent / "icons" / "webverse.ico"
		self.setWindowIcon(QIcon(str(icon_path)))

		# Normal top-level window WITH explicit decoration hints (KWin needs these for active maximize button).
		f = (
			Qt.Window
			| Qt.WindowSystemMenuHint
			| Qt.WindowMinimizeButtonHint
			| Qt.WindowMaximizeButtonHint
			| Qt.WindowCloseButtonHint
			| Qt.WindowMinMaxButtonsHint
		)
		self.setWindowFlags(f)

		# Keep it dead-simple: a normal resizable window
		self.resize(1920, 1080)

		self._history = []  # list[(stack_index, lab_id|None)]
		self._hist_index = -1
		self._suppress_history = False

		central = QWidget()
		self.setCentralWidget(central)

		# Global focus sink (so inputs drop :focus when clicking anywhere else)
		self._focus_sink = QWidget(central)
		self._focus_sink.setObjectName("FocusSink")
		self._focus_sink.setFocusPolicy(Qt.StrongFocus)
		self._focus_sink.setFixedSize(1, 1)
		self._focus_sink.setAttribute(Qt.WA_TransparentForMouseEvents, True)
		self._focus_sink.move(0, 0)

		QApplication.instance().installEventFilter(self)

		root = QVBoxLayout(central)
		root.setContentsMargins(0, 0, 0, 0)
		root.setSpacing(0)

		# Make sure the root is not “fixed”
		central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

		self.topbar = TopBar()
		root.addWidget(self.topbar)

		body = QFrame()
		body.setObjectName("AppShell")
		body_layout = QHBoxLayout(body)
		body_layout.setContentsMargins(14, 14, 14, 14)
		body_layout.setSpacing(12)
		body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

		self.stack = QStackedWidget()
		self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

		self.home = HomeView(state)
		self.browse = LabsBrowseView(state)
		self.profile = ProfileView(api_base_url=os.getenv("WEBVERSE_API_URL", "https://api-opensource.webverselabs.com/").rstrip("/"))
		self.lab_detail = LabDetailView(state)
		self.progress = ProgressView(state)
		self.settings = SettingsView(state)

		self.stack.addWidget(self.home)       # 0
		self.stack.addWidget(self.browse)     # 1
		self.stack.addWidget(self.lab_detail) # 2
		self.stack.addWidget(self.progress)   # 3
		self.stack.addWidget(self.settings)   # 4
		self.stack.addWidget(self.profile) # 5 (new)

		# Let Progress jump into a lab detail page on row click
		if hasattr(self.progress, "lab_selected"):
			try:
				self.progress.lab_selected.connect(self._select_and_open_lab)
			except Exception:
				pass

		self.sidebar = Sidebar(self.stack, profile_index=5)

		# Sidebar login/signup and auto device-login must propagate auth changes
		try:
			if hasattr(self.sidebar, "auth_changed"):
				self.sidebar.auth_changed.connect(self._on_auth_changed)
		except Exception:
			pass

		# When XP/rank changes (e.g. after a solve), refresh the sidebar badge.
		try:
			if hasattr(state, "player_stats_changed"):
				state.player_stats_changed.connect(self.sidebar.refresh_auth)
		except Exception:
			pass

		# Profile needs to be able to force-refresh auth UI after logout.
		try:
			self.profile.auth_changed.connect(self._on_auth_changed)
		except Exception:
			pass

		# Profile-requested toasts (sync failures, etc.)
		try:
			self.profile.toast_requested.connect(self.show_toast)
		except Exception:
			pass

		# Apply stylesheet first so the first toast sizes correctly
		self.setStyleSheet(qss_onyx_amber())

		# Global toast host overlay (after QSS)
		self.toast_host = ToastHost(self)
		self.toast_host.raise_()

		# Lab SOLVED celebration overlay
		self.solve_host = SolveCelebrationHost(self)
		self.solve_host.raise_()

		self._pending_update = None
		self.updater = UpdateManager(owner="LeighlinRamsay", repo="WebVerse", parent=self)
		self.updater.update_available.connect(self._on_update_available)
		self.updater.update_check_failed.connect(lambda err: self.toast_warn(f"Update check failed: {err}"))
		self.updater.start()


		body_layout.addWidget(self.sidebar)
		body_layout.addWidget(self.stack, 1)
		root.addWidget(body, 1)

		# Make sure overlay matches window size after first show/layout
		QTimer.singleShot(0, lambda: self.toast_host.resize(self.size()))

		self.palette = CommandPalette(state, self)
		self.palette.lab_selected.connect(self._select_and_open_lab)

		self.shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), self)
		self.shortcut_palette.activated.connect(self._open_palette)

		self.topbar.back_requested.connect(self._go_back)
		self.topbar.forward_requested.connect(self._go_forward)
		self.topbar.search_requested.connect(self._open_palette)
		self.topbar.running_requested.connect(self._open_running_lab)

		self.lab_detail.nav_back.connect(self._go_back)
		self.lab_detail.nav_forward.connect(self._go_forward)
		self.lab_detail.nav_to_labs.connect(lambda: self.navigate(1, push=True))

		self.state.running_changed.connect(self._update_running_pill)
		self._update_running_pill(self.state.running())

		# Live runtime operations (starting/stopping/resetting) -> TopBar pill
		try:
			if hasattr(self.state, "runtime_op_changed"):
				self.state.runtime_op_changed.connect(self._on_runtime_op_changed)
		except Exception:
			pass

		self.state.docker_changed.connect(lambda text, kind: self.sidebar.set_docker_status(text, kind))
		text, kind = self.state.docker_status()
		self.sidebar.set_docker_status(text, kind)

		self.home.nav_labs.connect(lambda: self.navigate(1, push=True))
		self.home.request_select_lab.connect(self._select_and_open_lab)
		self.browse.request_open_lab.connect(self._select_and_open_lab)

		self.stack.currentChanged.connect(self._on_stack_changed)

		self.navigate(0, push=True)

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.state.refresh_docker)
		self.timer.start(12000)

	def _on_auth_changed(self):
		"""
		Central auth-change handler (login/logout/account switch).
		- Refresh sidebar lock state
		- Invalidate caches so Home/Profile/Sidebar update immediately
		"""
		try:
			self.sidebar.refresh_auth()
		except Exception:
			pass

		# Always force an auth refresh across the app (login OR logout).
		try:
			if hasattr(self.state, "on_auth_changed"):
				self.state.on_auth_changed()
			else:
				# fallback: at least clear caches so UI repaints
				if hasattr(self.state, "clear_user_caches"):
					self.state.clear_user_caches()

				else:
					# Logged in: force Home/sidebar/etc to refresh stats immediately
					try:
						self.state.player_stats_changed.emit()
					except Exception:
						pass
		except Exception:
			pass

	def _on_update_available(self, info):
		self._pending_update = info
		self.show_toast(
			"Update available",
			f"WebVerse v{info.latest_version} is available. Click to open releases.",
			variant="info",
			ms=3200,
		)

	def open_update_page(self):
		if not self._pending_update:
			return
		try:
			QDesktopServices.openUrl(QUrl(self._pending_update.url))
		except Exception:
			pass

	def _post_show_unlock_and_audit(self):
		"""
		Runs after the native window exists.
		1) Force-unlock resizing hints on the main window  core containers.
		2) Print offenders that would disable maximize (fixed min=max, SetFixedSize layouts, etc).
		"""
		# ---- 1) Force-unlock top-level sizing ----
		try:
			self.setMinimumSize(QSize(0, 0))
			self.setMaximumSize(QSize(16777215, 16777215))
			self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		except Exception:
			pass

		cw = self.centralWidget()
		if cw:
			try:
				cw.setMinimumSize(QSize(0, 0))
				cw.setMaximumSize(QSize(16777215, 16777215))
				cw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
			except Exception:
				pass

		for w in (getattr(self, "stack", None),):
			if w:
				try:
					w.setMinimumSize(QSize(0, 0))
					w.setMaximumSize(QSize(16777215, 16777215))
					w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
				except Exception:
					pass

		# ---- 2) Audit widget tree for “maximize killers” ----
		offenders = []

		def check_widget(widget: QWidget):
			try:
				mn = widget.minimumSize()
				mx = widget.maximumSize()
				fixed = (mn.width() == mx.width()) and (mn.height() == mx.height()) and (mn.width() > 0) and (mn.height() > 0)
				if fixed:
					offenders.append(("FIXED_WIDGET", widget, mn, mx))
				# suspicious max size (someone set maximumSize to something small)
				if (mx.width() < 16777215 or mx.height() < 16777215) and not fixed:
					offenders.append(("MAX_LIMIT", widget, mn, mx))
			except Exception:
				pass

			lay = widget.layout()
			if lay is not None:
				try:
					if lay.sizeConstraint() == QLayout.SetFixedSize:
						offenders.append(("FIXED_LAYOUT", widget, None, None))
				except Exception:
					pass

		check_widget(self)
		if cw:
			check_widget(cw)
			for child in cw.findChildren(QWidget):
				check_widget(child)

		print("\n--- RESIZE AUDIT ---")
		print("window min:", self.minimumSize().width(), self.minimumSize().height())
		print("window max:", self.maximumSize().width(), self.maximumSize().height())
		print("fixed?:", self.minimumSize() == self.maximumSize())
		for kind, widget, mn, mx in offenders[:80]:
			name = widget.objectName() or widget.__class__.__name__
			if kind == "FIXED_LAYOUT":
				print(f"[{kind}] {name} -> layout.sizeConstraint == SetFixedSize")
			else:
				print(f"[{kind}] {name} -> min={mn.width()}x{mn.height()} max={mx.width()}x{mx.height()}")
		print("--- END AUDIT ---\n")

	def show_toast(self, title: str, body: str = "", variant: str = "info", ms: int = 2000):
		"""
		Canonical toast API for the whole app:
		  show_toast("Title", "Body", variant="error", ms=2500)

		Backward compat:
		  show_toast("message", "error", 3000)
		"""
		# Backward compat path: show_toast(message, level, timeout)
		if variant in ("info", "success", "warn", "error") and isinstance(ms, int) and body and body in ("info", "success", "warn", "error"):
			# Someone called show_toast(message, level, timeout)
			# Here: title=message, body=level, variant=timeout (wrong) — normalize:
			level = body
			timeout = variant if isinstance(variant, int) else ms
			self.toast_host.show_toast("Info" if level == "info" else level.title(), title, variant=level, ms=int(timeout))
			return

		self.toast_host.show_toast(title, body, variant=variant, ms=ms)

	def toast_success(self, msg: str, ms: int = 1800):
		self.show_toast("Success", msg, variant="success", ms=ms)

	def toast_error(self, msg: str, ms: int = 2400):
		self.show_toast("Error", msg, variant="error", ms=ms)

	def toast_warn(self, msg: str, ms: int = 2200):
		self.show_toast("Warning", msg, variant="warn", ms=ms)

	def toast_info(self, msg: str, ms: int = 2000):
		self.show_toast("Info", msg, variant="info", ms=ms)


	def _open_palette(self):
		self.palette.open_centered()

	def _update_running_pill(self, lab):
		# Default behavior (running/stopped) is still valid, but can be overridden
		# by transient op states coming from runtime_op_changed.

		try:
			# If a transient op is active for some lab, do NOT override the pill here.
			# Otherwise: navigating away/back will reset the pill to stopped/running
			# until the operation completes.
			if hasattr(self.state, "runtime_op_lab_id") and callable(getattr(self.state, "runtime_op_lab_id")):
				if self.state.runtime_op_lab_id():
					op = getattr(self.state, "_runtime_op", "")  # best-effort
					if (op or "").strip().lower() in ("starting", "stopping", "resetting"):
						return
		except Exception:
			pass


		if lab:
			label = f"{lab.name}  •  click to open"
			try:
				# If we don't have an active op, show RUNNING
				self.topbar.set_status("running", lab.id, label)
			except Exception:
				self.topbar.set_running(lab.id, label)
		else:
			try:
				self.topbar.set_status("stopped", None, None)
			except Exception:
				self.topbar.set_running(None, None)

	def _on_runtime_op_changed(self, lab_id: str, op: str):
		op = (op or "").strip().lower()
		lab_id = (lab_id or "").strip()

		if op == "stopped":
			try:
				self.topbar.set_status("stopped", None, None)
			except Exception:
				self.topbar.set_running(None, None)
			return

		lab = next((x for x in self.state.labs() if str(x.id) == str(lab_id)), None)
		#label = f"{lab.name}  •  click to open" if lab else "Lab  •  click to open" if lab_id else ""

		if lab:
			label = f"{lab.name}  •  click to open"

		else:
			if lab_id:
				label = "Lab  •  click to open"
			else:
				label = ""

		# starting: green, stopping: red, resetting: yellow, running: green
		try:
			self.topbar.set_status(op, lab_id or (lab.id if lab else None), label)
		except Exception:
			# fallback: show as running/stopped if older topbar
			if op in ("running", "starting", "resetting", "stopping") and lab_id:
				self.topbar.set_running(lab_id, label)
			else:
				self.topbar.set_running(None, None)

	def _open_running_lab(self):
		# Must work even when a lab is STARTING/STOPPING/RESETTING (not "running" yet).
		lab_id = None

		# 1) If TopBar exposes a current/active lab id, prefer it.
		for attr in ("running_lab_id", "status_lab_id", "current_lab_id"):
			try:
				fn = getattr(self.topbar, attr, None)
				if callable(fn):
					lab_id = fn()
					if lab_id:
						break
			except Exception:
				pass

		# 2) Fall back to AppState transient op lab id (starting/resetting) if present.
		if not lab_id:
			try:
				if hasattr(self.state, "runtime_op_lab_id") and callable(getattr(self.state, "runtime_op_lab_id")):
					lab_id = self.state.runtime_op_lab_id()
			except Exception:
				lab_id = None

		# 3) Fall back to the actual running lab.
		if not lab_id:
			try:
				lab = self.state.running()
				lab_id = lab.id if lab else None
			except Exception:
				lab_id = None

		if lab_id:
			self._select_and_open_lab(str(lab_id))

	def _on_stack_changed(self, index: int):
		if self._suppress_history:
			return

		lab_id = None
		if index == 2 and self.state.selected():
			lab_id = self.state.selected().id

		self._push_history(index, lab_id)

	def _push_history(self, stack_index: int, lab_id: str | None):
		if self._hist_index < len(self._history) - 1:
			self._history = self._history[: self._hist_index + 1]

		if self._history and self._history[-1] == (stack_index, lab_id):
			self._hist_index = len(self._history) - 1
			self._update_nav_buttons()
			return

		self._history.append((stack_index, lab_id))
		self._hist_index = len(self._history) - 1
		self._update_nav_buttons()

	def _update_nav_buttons(self):
		can_back = self._hist_index > 0
		can_fwd = self._hist_index < (len(self._history) - 1)
		self.topbar.set_nav_enabled(can_back, can_fwd)

		if hasattr(self.lab_detail, "btn_back"):
			self.lab_detail.btn_back.setEnabled(can_back)
		if hasattr(self.lab_detail, "btn_fwd"):
			self.lab_detail.btn_fwd.setEnabled(can_fwd)

	def _go_back(self):
		if self._hist_index <= 0:
			return
		self._hist_index -= 1
		stack_index, lab_id = self._history[self._hist_index]
		self.navigate(stack_index, lab_id=lab_id, push=False)

	def _go_forward(self):
		if self._hist_index >= len(self._history) - 1:
			return
		self._hist_index += 1
		stack_index, lab_id = self._history[self._hist_index]
		self.navigate(stack_index, lab_id=lab_id, push=False)

	def _device_is_linked(self) -> bool:
		"""
		Only apply access restrictions when the device is linked to an account.
		If the device was never linked, the GUI remains fully usable as a guest.
		"""
		from webverse.core import progress_db

		for fn_name in ("is_device_linked", "device_is_linked", "is_device_linked_to_account", "device_linked"):
			try:
				fn = getattr(progress_db, fn_name, None)
				if callable(fn):
					return bool(fn())
			except Exception:
				pass

		try:
			v = self._settings.value("auth/device_linked", None)
			if v is not None:
				if isinstance(v, str):
					return v.strip().lower() in ("1", "true", "yes", "y", "on")
				return bool(v)
		except Exception:
			pass

		try:
			u = str(self._settings.value("auth/username", "") or "").strip()
			return bool(u)
		except Exception:
			return False

	def _is_logged_in(self) -> bool:
		# IMPORTANT: keep GUI "logged in" definition in sync with core auth logic.
		# progress_db.is_logged_in() is token-based; username may not exist in OSS.
		try:
			from webverse.core import progress_db as _pdb
			fn = getattr(_pdb, "is_logged_in", None)
			if callable(fn):
				return bool(fn())
		except Exception:
			pass
		try:
			token = str(self._settings.value("auth/access_token", "") or "").strip()
			return bool(token)
		except Exception:
			return False

	def navigate(self, stack_index: int, lab_id: str | None = None, push: bool = True):
		# IMPORTANT:
		# Do NOT block overall GUI access when logged out.
		# Only *disable/guard* certain pages when the device is linked to an account.
		# (Guest/offline devices should be fully usable.)
		try:
			linked = self._device_is_linked()
			logged_in = self._is_logged_in()
			locked = bool(linked and (not logged_in))

			# - Browse (1)
			# - Lab Detail (2)
			# - Progress (3)
			# - Settings (4)
			# - Profile (5)
			if locked and stack_index in (1, 2, 3, 4, 5):
				self.show_toast("Login required", "Login to access locked pages", variant="warn", ms=2200)
				stack_index = 0
				lab_id = None
		except Exception:
			pass

		self._suppress_history = True
		try:
			if stack_index == 2 and lab_id:
				self._select_lab_only(lab_id)
				self.sidebar.set_page(2)
			else:
				self.sidebar.set_page(stack_index)
		finally:
			self._suppress_history = False

		if push:
			self._push_history(stack_index, lab_id)

		self._update_nav_buttons()

		# Auto-refresh profile on every navigation to it.
		if stack_index == 5:
			try:
				if hasattr(self.profile, "on_activated"):
					self.profile.on_activated()
			except Exception:
				pass

	def _select_lab_only(self, lab_id: str):
		lab = next((x for x in self.state.labs() if x.id == lab_id), None)
		if lab:
			self.state.set_selected(lab)
			self.lab_detail.set_lab(lab)

	def _select_and_open_lab(self, lab_id: str):
		# Hard guard: even if a lab tile/list item is clicked, do nothing when locked.
		try:
			linked = self._device_is_linked()
			logged_in = self._is_logged_in()
			if linked and (not logged_in):
				self.show_toast("Login required", "Login to open labs", variant="warn", ms=2200)
				return
		except Exception:
			pass

		self._select_lab_only(lab_id)
		self.navigate(2, lab_id=lab_id, push=True)

	def _ancestor_is_input(self, obj) -> bool:
		w = obj
		while w is not None:
			if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox)):
				return True
			w = w.parent()
		return False

	def _sink_focus(self):
		fw = QApplication.focusWidget()

		# close combo popup if the focused widget is a combo
		if isinstance(fw, QComboBox):
			try:
				if fw.view() and fw.view().isVisible():
					fw.hidePopup()
			except Exception:
				pass

		self._focus_sink.setFocus(Qt.MouseFocusReason)

	def closeEvent(self, event):
		# Ensure lab notes are persisted even if the user closes immediately.
		try:
			if hasattr(self, "lab_detail") and hasattr(self.lab_detail, "flush_notes"):
				self.lab_detail.flush_notes()
		except Exception:
			pass
		return super().closeEvent(event)

	def eventFilter(self, obj, event):
		if event.type() == QEvent.MouseButtonPress:
			fw = QApplication.focusWidget()

			# only do anything if an input currently has focus
			if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox)):
				# If a popup (combo/menu/etc) is open and we clicked inside it, don't sink focus.
				popup = QApplication.activePopupWidget()
				if popup is not None:
					gp = event.globalPos()
					if popup.rect().contains(popup.mapFromGlobal(gp)):
						return super().eventFilter(obj, event)

				# If we clicked an input (or inside one), don't sink focus.
				if self._ancestor_is_input(obj):
					return super().eventFilter(obj, event)

				# Otherwise: click-away => sink focus (this covers Sidebar/TopBar too)
				self._sink_focus()

		return super().eventFilter(obj, event)
