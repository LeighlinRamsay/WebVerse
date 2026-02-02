# gui/views/lab_detail.py
from __future__ import annotations

import os
import math
import time
import socket
import re
from pathlib import Path
from collections import deque
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
	QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
	QPushButton, QLineEdit, QTextEdit, QTabWidget, QSplitter, QToolButton, QStyle, QSizePolicy, QStackedWidget, QGraphicsDropShadowEffect,
	QScrollArea
)

from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal, QUrl, QTimer, QEvent, QSize, QRect, QRectF, QPoint
from PyQt5.QtGui import QDesktopServices, QIcon, QPainter, QColor, QPen, QPixmap, QFontMetrics
from PyQt5.QtWidgets import QApplication, QLayout

from webverse.gui.util_avatar import lab_circle_icon, lab_badge_icon
from webverse.core import docker_ops
from webverse.core import progress_db
from webverse.core.runtime import set_running_lab, get_running_lab
from webverse.gui.widgets.toast import ToastHost


class _DockerWorker(QObject):
	finished = pyqtSignal(bool, str)

	def __init__(self, fn, *args, **kwargs):
		super().__init__()
		self.fn = fn
		self.args = args
		self.kwargs = kwargs

	def run(self):
		try:
			p = self.fn(*self.args, **self.kwargs)
			out = (p.stdout or "").strip()
			err = (p.stderr or "").strip()
			ok = (p.returncode == 0)

			msg = out if out else ""
			if err:
				msg = (msg + ("\n" if msg else "") + err).strip()

			self.finished.emit(ok, msg)
		except Exception as e:
			self.finished.emit(False, str(e))


def _section(title: str):
	f = QFrame()
	f.setObjectName("Section")
	l = QVBoxLayout(f)
	l.setContentsMargins(0, 0, 0, 0)
	l.setSpacing(8)
	if title:
		h = QLabel(title)
		h.setObjectName("SectionTitle")
		l.addWidget(h)
	return f, l


def _info_card(title: str) -> tuple[QFrame, QVBoxLayout]:
	card = QFrame()
	card.setObjectName("InfoCard")
	card.setAttribute(Qt.WA_StyledBackground, True)
	lay = QVBoxLayout(card)
	lay.setContentsMargins(14, 14, 14, 14)
	lay.setSpacing(10)

	if title:
		h = QLabel(title)
		h.setObjectName("InfoSectionTitle")
		lay.addWidget(h)

	return card, lay


def _info_divider() -> QFrame:
	d = QFrame()
	d.setObjectName("InfoDivider")
	d.setFixedHeight(1)
	d.setAttribute(Qt.WA_StyledBackground, True)
	return d


def _icon_btn(obj: str, tooltip: str, icon: QIcon) -> QToolButton:
	b = QToolButton()
	b.setObjectName(obj)
	b.setCursor(Qt.PointingHandCursor)
	b.setToolTip(tooltip)
	b.setAutoRaise(True)
	b.setToolButtonStyle(Qt.ToolButtonIconOnly)
	b.setFixedSize(34, 34)
	b.setIconSize(QSize(18, 18))
	b.setIcon(icon)
	return b


def _kv_row(key: str, mono: bool = False) -> tuple[QFrame, QLabel, QHBoxLayout]:
	"""
	Returns (row_frame, value_label, right_layout_for_buttons)
	"""
	row = QFrame()
	row.setObjectName("InfoRow")
	row.setAttribute(Qt.WA_StyledBackground, True)

	h = QHBoxLayout(row)
	h.setContentsMargins(12, 10, 12, 10)
	h.setSpacing(10)

	k = QLabel(key)
	k.setObjectName("InfoKey")
	h.addWidget(k, 0)

	v = QLabel("—")
	v.setObjectName("InfoMono" if mono else "InfoValue")
	v.setTextInteractionFlags(Qt.TextSelectableByMouse)
	v.setWordWrap(True)
	h.addWidget(v, 1)

	right = QHBoxLayout()
	right.setSpacing(8)
	h.addLayout(right, 0)

	return row, v, right


class _MiniSpinner(QWidget):
	def __init__(self, parent=None, size=22):
		super().__init__(parent)
		self.setObjectName("ConnSpinner")
		self._angle = 0
		self._timer = QTimer(self)
		self._timer.setInterval(30)
		self._timer.timeout.connect(self._tick)
		self._color = QColor(34, 197, 94)  # default green
		self.setFixedSize(size, size)

	def set_color(self, qcolor: QColor):
		self._color = qcolor
		self.update()

	def start(self):
		if not self._timer.isActive():
			self._timer.start()

	def stop(self):
		self._timer.stop()

	def _tick(self):
		self._angle = (self._angle + 10) % 360
		self.update()

	def paintEvent(self, _ev):
		p = QPainter(self)
		p.setRenderHint(QPainter.Antialiasing, True)

		w = self.width()
		h = self.height()
		r = min(w, h) / 2.0

		# ring geometry
		pen_w = max(2, int(r * 0.18))
		rect = QRectF(
			(w - 2 * (r - pen_w)) / 2,
			(h - 2 * (r - pen_w)) / 2,
			2 * (r - pen_w),
			2 * (r - pen_w),
		)

		pen = QPen(self._color, pen_w, Qt.SolidLine, Qt.RoundCap)
		p.setPen(pen)

		# draw a 270-degree arc so it looks like a "spinner"
		start_angle = int((-self._angle) * 16)
		span_angle = int(270 * 16)
		p.drawArc(rect, start_angle, span_angle)


def _make_copy_icon(color: QColor, size: int = 18) -> QIcon:
	pm = QPixmap(size, size)
	pm.fill(Qt.transparent)

	p = QPainter(pm)
	p.setRenderHint(QPainter.Antialiasing, True)

	pen = QPen(color)
	pen.setWidth(2)
	p.setPen(pen)
	p.setBrush(Qt.transparent)

	# back sheet
	p.drawRoundedRect(3, 5, 10, 10, 2, 2)
	# front sheet
	p.drawRoundedRect(6, 2, 10, 10, 2, 2)

	p.end()
	return QIcon(pm)

class _EntrypointLabel(QLabel):
	"""
	A QLabel that only counts clicks if the user actually clicked on the text glyphs area.
	This keeps QSS untouched (plain text label) while preventing "click the empty box" copies.
	"""
	clicked_on_text = pyqtSignal()

	def __init__(self, parent=None):
		super().__init__(parent)
		self._press_pos: Optional[QPoint] = None
		self._pressed_on_text: bool = False

		# Keep your existing behavior (selectable text) if you want.
		# We prevent accidental copy by requiring click-without-drag.
		self.setTextInteractionFlags(Qt.TextSelectableByMouse)

	def _text_rect(self) -> QRect:
		"""
		Estimate the actual rect where the text is drawn inside the label,
		taking alignment + contentsRect into account.
		"""
		cr = self.contentsRect()
		txt = self.text() or ""
		if not txt:
			return QRect(0, 0, 0, 0)

		fm = QFontMetrics(self.font())
		# boundingRect gives us a tight-ish box around the glyphs.
		br = fm.boundingRect(txt)
		tw = br.width()
		th = br.height()

		# Horizontal alignment
		align = self.alignment()
		x = cr.x()
		if align & Qt.AlignHCenter:
			x = cr.x() + max(0, (cr.width() - tw) // 2)
		elif align & Qt.AlignRight:
			x = cr.x() + max(0, (cr.width() - tw))

		# Vertical alignment (default is usually VCenter for labels)
		y = cr.y()
		if align & Qt.AlignVCenter:
			y = cr.y() + max(0, (cr.height() - th) // 2)
		elif align & Qt.AlignBottom:
			y = cr.y() + max(0, (cr.height() - th))

		return QRect(x, y, tw, th)

	def mousePressEvent(self, ev):
		if ev.button() == Qt.LeftButton:
			self._press_pos = ev.pos()
			self._pressed_on_text = self._text_rect().contains(ev.pos())
		super().mousePressEvent(ev)

	def mouseReleaseEvent(self, ev):
		super().mouseReleaseEvent(ev)
		if ev.button() != Qt.LeftButton:
			return
		if not self._press_pos:
			return
		# If user dragged (selecting), don't treat it as a click-to-copy.
		if (ev.pos() - self._press_pos).manhattanLength() > 3:
			return
		if self._pressed_on_text and self._text_rect().contains(ev.pos()):
			self.clicked_on_text.emit()

class _ConnBar(QFrame):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setObjectName("ConnBar")
		self.setAttribute(Qt.WA_StyledBackground, True)

		self._url: str | None = None
		self._state: str = "stopped"  # stopped | starting | running | stopping | resetting
		self.entrypoint_clicked = pyqtSignal(str)

		root = QHBoxLayout(self)
		root.setContentsMargins(16, 14, 16, 14)
		root.setSpacing(14)

		# -------------------------
		# LEFT: stacked content (Start / Busy / Running)
		# -------------------------
		self.left_stack = QStackedWidget()
		self.left_stack.setObjectName("ConnLeftStack")
		root.addWidget(self.left_stack, 1)

		# Page 0: STOPPED -> Start button
		p0 = QWidget()
		p0l = QHBoxLayout(p0)
		p0l.setContentsMargins(0, 0, 0, 0)
		p0l.setSpacing(0)

		self.btn_start = QPushButton("Start Lab")
		self.btn_start.setObjectName("ConnStartBig")
		self.btn_start.setCursor(Qt.PointingHandCursor)
		p0l.addWidget(self.btn_start, 0, Qt.AlignVCenter)

		p0l.addStretch(1)
		self.left_stack.addWidget(p0)

		# Page 1: BUSY -> spinner + text
		p1 = QWidget()
		p1l = QHBoxLayout(p1)
		p1l.setContentsMargins(0, 0, 0, 0)
		p1l.setSpacing(12)

		self.spinner = _MiniSpinner(size=22)
		p1l.addWidget(self.spinner, 0, Qt.AlignVCenter)

		self.busy_text = QLabel("Lab is spawning, Please wait...")
		self.busy_text.setObjectName("ConnBusyText")
		self.busy_text.setWordWrap(False)
		p1l.addWidget(self.busy_text, 0, Qt.AlignVCenter)

		p1l.addStretch(1)
		self.left_stack.addWidget(p1)

		# Page 2: RUNNING -> entrypoint + copy icon
		p2 = QWidget()
		p2l = QHBoxLayout(p2)
		p2l.setContentsMargins(0, 0, 0, 0)
		p2l.setSpacing(10)  # they must NOT touch

		# after creating self.left_stack, p0, p1, p2
		for w in (self.left_stack, p0, p1, p2):
			w.setAttribute(Qt.WA_StyledBackground, True)
			w.setStyleSheet("background: transparent;")

		self.value = _EntrypointLabel()
		self.value.setObjectName("ConnValue")
		self.value.setFocusPolicy(Qt.NoFocus)
		self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
		self.value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
 

		# subtle amber aura around the entrypoint text
		_val_glow = QGraphicsDropShadowEffect(self.value)
		_val_glow.setBlurRadius(52)
		_val_glow.setOffset(0, 0)
		_val_glow.setColor(QColor(245, 197, 66, 200))
		self.value.setGraphicsEffect(_val_glow)

		self.value.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
		p2l.addWidget(self.value, 0, Qt.AlignVCenter)

		self.copy_btn = QToolButton()
		self.copy_btn.setObjectName("CopyBtn")
		self.copy_btn.setCursor(Qt.PointingHandCursor)
		self.copy_btn.setToolTip("Copy to clipboard")
		self.copy_btn.setAutoRaise(True)
		self.copy_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
		self.copy_btn.setFixedSize(34, 34)
		self.copy_btn.setIconSize(QSize(18, 18))

		amber = QColor(245, 197, 66)
		self.copy_btn.setIcon(_make_copy_icon(amber, 18))
		p2l.addWidget(self.copy_btn, 0, Qt.AlignVCenter)

		# IMPORTANT: prevents the label from expanding and pushing the icon away
		p2l.addStretch(1)

		self.left_stack.addWidget(p2)

		# -------------------------
		# RIGHT: status pill + Stop/Reset
		# -------------------------
		right = QVBoxLayout()
		right.setSpacing(8)
		right.setAlignment(Qt.AlignTop)

		self.pill = QLabel("STOPPED")
		self.pill.setVisible(False)  # pill is now in the tab bar corner

		btnrow = QHBoxLayout()
		btnrow.setSpacing(10)

		self.btn_stop = QPushButton("Stop")
		self.btn_stop.setObjectName("ConnStopBtn")
		self.btn_stop.setCursor(Qt.PointingHandCursor)

		try:
			self.btn_stop.setIcon(QApplication.style().standardIcon(QStyle.SP_MediaStop))
		except Exception:
			pass

		btnrow.addWidget(self.btn_stop)

		self.btn_reset = QPushButton("Reset")
		self.btn_reset.setObjectName("ConnResetBtn")
		self.btn_reset.setCursor(Qt.PointingHandCursor)

		try:
			self.btn_reset.setIcon(QApplication.style().standardIcon(QStyle.SP_BrowserReload))
		except Exception:
			pass

		btnrow.addWidget(self.btn_reset)

		def _add_glow(w, color: QColor):
			eff = QGraphicsDropShadowEffect(w)
			eff.setBlurRadius(28)
			eff.setOffset(0, 0)
			eff.setColor(color)
			w.setGraphicsEffect(eff)

		_add_glow(self.btn_stop, QColor(239, 68, 68, 95))    # danger glow
		_add_glow(self.btn_reset, QColor(245, 197, 66, 120)) # amber glow

		right.addLayout(btnrow)
		root.addLayout(right, 0)

		 # Create a real signal on the instance (PyQt doesn't love defining pyqtSignal dynamically on class)
		# but we can forward via a normal signal defined on LabDetailView.
		# Instead: we emit via a callback attribute set by LabDetailView (see LabDetailView wiring).

		# When the user clicks on text glyph area, we call a handler if installed.
		self._on_entrypoint_text_clicked = None
		def _clicked():
			if callable(self._on_entrypoint_text_clicked):
				self._on_entrypoint_text_clicked()
		self.value.clicked_on_text.connect(_clicked)

		self._apply_state("stopped")

	def set_url(self, url):
		"""
		Accepts:
		  - str: "http://..."
		  - dict: {"base_url": "..."} etc.
		  - None
		Normalizes into a display string and a copyable URL.
		Returns the resolved string (or "").
		"""
		def _first_string(d: dict, keys: tuple[str, ...]) -> str:
			for k in keys:
				v = d.get(k)
				if isinstance(v, str) and v.strip():
					return v.strip()
			return ""

		resolved = ""

		if url is None:
			resolved = ""
		elif isinstance(url, str):
			resolved = url.strip()
		elif isinstance(url, dict):
			# ✅ your lab uses base_url
			resolved = _first_string(
				url,
				(
					"base_url", "baseUrl",
					"url", "entrypoint", "endpoint",
					"public_url", "publicUrl",
					"http", "https",
					"host_url", "hostUrl",
					"address",
				),
			)

			# If the dict has exactly one string value, use it
			if not resolved:
				try:
					if len(url) == 1:
						only_val = next(iter(url.values()))
						if isinstance(only_val, str) and only_val.strip():
							resolved = only_val.strip()
				except Exception:
					pass

			# host/port form
			if not resolved:
				host = url.get("host") or url.get("hostname")
				port = url.get("port")
				scheme = url.get("scheme") or "http"
				if isinstance(host, str) and host.strip() and port is not None:
					resolved = f"{scheme}://{host.strip()}:{port}"
				elif isinstance(host, str) and host.strip():
					resolved = host.strip()

			# last resort: keep blank instead of showing "{'base_url': ...}"
			if not resolved:
				resolved = ""

		else:
			resolved = str(url).strip() if url is not None else ""

		self._url = resolved or None

		# update UI if currently running
		if self._state == "running":
			self.value.setText(self._url or "(none)")
			self.copy_btn.setEnabled(bool(self._url))

		return self._url or ""

	def url(self) -> str:
		return self._url or ""

	def set_state(self, state: str):
		self._apply_state(state)

	def _apply_state(self, state: str):
		self._state = state

		amber = QColor(245, 197, 66)
		green = QColor(34, 197, 94)
		red = QColor(239, 68, 68)

		if state == "starting":
			self.left_stack.setCurrentIndex(1)
			self.busy_text.setText("Lab is spawning, Please wait...")
			self.busy_text.setProperty("variant", "spawn")
			self.spinner.set_color(green)
			self.spinner.start()

			self.pill.setText("SPAWNING")
			self.pill.setObjectName("MetaPillWarn")

			self.btn_start.setEnabled(False)
			self.btn_stop.setEnabled(False)
			self.btn_reset.setEnabled(False)

		elif state == "stopping":
			self.left_stack.setCurrentIndex(1)
			self.busy_text.setText("Lab is being Terminated, Please wait...")
			self.busy_text.setProperty("variant", "stop")
			self.spinner.set_color(red)
			self.spinner.start()

			self.pill.setText("TERMINATING")
			self.pill.setObjectName("MetaPillBad")

			self.btn_start.setEnabled(False)
			self.btn_stop.setEnabled(False)
			self.btn_reset.setEnabled(False)

		elif state == "resetting":
			self.left_stack.setCurrentIndex(1)
			self.busy_text.setText("Lab is being reset, Please wait...")
			self.busy_text.setProperty("variant", "reset")
			self.spinner.set_color(amber)
			self.spinner.start()

			self.pill.setText("RESETTING")
			self.pill.setObjectName("MetaPillWarn")

			self.btn_start.setEnabled(False)
			self.btn_stop.setEnabled(False)
			self.btn_reset.setEnabled(False)

		elif state == "running":
			self.left_stack.setCurrentIndex(2)
			self.spinner.stop()

			self.value.setText(self._url or "(none)")
			self.copy_btn.setEnabled(bool(self._url))

			self.pill.setText("RUNNING")
			self.pill.setObjectName("MetaPillOk")

			self.btn_start.setEnabled(False)
			self.btn_stop.setEnabled(True)
			self.btn_reset.setEnabled(True)

		else:
			# stopped
			self.left_stack.setCurrentIndex(0)
			self.spinner.stop()

			self.pill.setText("STOPPED")
			self.pill.setObjectName("MetaPillMuted")

			self.btn_start.setEnabled(True)
			self.btn_stop.setEnabled(False)
			self.btn_reset.setEnabled(False)

		# force QSS refresh on pill + busy text
		self.pill.style().unpolish(self.pill)
		self.pill.style().polish(self.pill)
		self.pill.update()

		self.busy_text.style().unpolish(self.busy_text)
		self.busy_text.style().polish(self.busy_text)
		self.busy_text.update()


class LabDetailView(QWidget):
	# navigation (wired by MainWindow)
	nav_back = pyqtSignal()
	nav_forward = pyqtSignal()
	nav_to_labs = pyqtSignal()

	def __init__(self, state):
		super().__init__()

		self._activity_lines = deque(maxlen=300)

		# --- docker worker thread state (must exist before any button callbacks fire) ---
		# Some UI paths (e.g., Logs → Refresh) can trigger _run_docker early; if these
		# aren't initialized, you'll crash with AttributeError on self._thread.
		self._thread = None
		self._worker = None

		self.state = state
		self._lab = None

		self._uptime_timer = QTimer(self)
		self._uptime_timer.setInterval(900)
		self._uptime_timer.timeout.connect(self._tick_uptime)

		self._op_state = "stopped"

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(12)

		# Breadcrumbs + Back/Forward (visual only; MainWindow owns history)
		self.breadcrumb_bar = QFrame()
		self.breadcrumb_bar.setObjectName("BreadcrumbBar")
		self.breadcrumb_bar.setAttribute(Qt.WA_StyledBackground, True)
		bb = QHBoxLayout(self.breadcrumb_bar)
		bb.setContentsMargins(14, 10, 14, 0)
		bb.setSpacing(10)

		self.btn_back = QToolButton()
		self.btn_back.setObjectName("NavBtn")
		self.btn_back.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
		self.btn_back.setCursor(Qt.PointingHandCursor)
		self.btn_back.setToolTip("Back")
		self.btn_back.setAutoRaise(True)
		self.btn_back.setEnabled(False)
		self.btn_back.clicked.connect(lambda: self.nav_back.emit())
		bb.addWidget(self.btn_back, 0, Qt.AlignVCenter)

		self.btn_forward = QToolButton()
		self.btn_forward.setObjectName("NavBtn")
		self.btn_forward.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
		self.btn_forward.setCursor(Qt.PointingHandCursor)
		self.btn_forward.setToolTip("Forward")
		self.btn_forward.setAutoRaise(True)
		self.btn_forward.setEnabled(False)
		self.btn_forward.clicked.connect(lambda: self.nav_forward.emit())
		bb.addWidget(self.btn_forward, 0, Qt.AlignVCenter)

		self.crumb_labs = QToolButton()
		self.crumb_labs.setObjectName("CrumbLink")
		self.crumb_labs.setText("Labs")
		self.crumb_labs.setCursor(Qt.PointingHandCursor)
		self.crumb_labs.setAutoRaise(True)
		self.crumb_labs.clicked.connect(lambda: self.nav_to_labs.emit())
		bb.addWidget(self.crumb_labs, 0, Qt.AlignVCenter)

		self.crumb_sep = QLabel(" / ")
		self.crumb_sep.setObjectName("CrumbSep")
		bb.addWidget(self.crumb_sep, 0, Qt.AlignVCenter)

		self.crumb_current = QLabel("—")
		self.crumb_current.setObjectName("CrumbCurrent")
		self.crumb_current.setTextInteractionFlags(Qt.TextSelectableByMouse)
		bb.addWidget(self.crumb_current, 1, Qt.AlignVCenter)

		bb.addStretch(1)
		outer.addWidget(self.breadcrumb_bar, 0)

		surface = QFrame()
		surface.setObjectName("ContentSurface")
		surface.setAttribute(Qt.WA_StyledBackground, True)
		outer.addWidget(surface, 1)

		s = QVBoxLayout(surface)
		s.setContentsMargins(18, 14, 18, 16)
		s.setSpacing(12)

		# Top row: Title + Meta
		top = QHBoxLayout()
		top.setSpacing(12)

		self.avatar = QLabel()
		self.avatar.setFixedSize(72, 72)
		self.avatar.setAlignment(Qt.AlignCenter)
		self.avatar.setObjectName("LabAvatar")
		top.addWidget(self.avatar, 0, Qt.AlignTop)

		title_col = QVBoxLayout()
		title_col.setSpacing(4)

		self.lab_name = QLabel("Select a lab")
		self.lab_name.setObjectName("H1")
		title_col.addWidget(self.lab_name)

		top.addLayout(title_col, 1)

		s.addLayout(top)

		# Entrypoint/Actions bar (ConnBar)
		self.conn = _ConnBar()
		s.addWidget(self.conn)

		# Tabs (full width, no right sidebar)
		self.tabs = QTabWidget()
		self.tabs.setObjectName("DetailTabs")
		s.addWidget(self.tabs, 1)

		# Let the corner widget have room (don't let tabs expand to consume all width)
		try:
			self.tabs.setUsesScrollButtons(True)
			tb = self.tabs.tabBar()
			tb.setExpanding(False)
			tb.setElideMode(Qt.ElideRight)
		except Exception:
			pass

		# Overview tab: Story first, then Flag submit panel (simple + fancy)
		self.overview = QWidget()
		ov = QVBoxLayout(self.overview)
		ov.setContentsMargins(0, 0, 0, 0)
		ov.setSpacing(0)

		self.overview_scroll = QScrollArea()
		self.overview_scroll.setObjectName("OverviewScroll")
		self.overview_scroll.setWidgetResizable(True)
		self.overview_scroll.setFrameShape(QFrame.NoFrame)
		ov.addWidget(self.overview_scroll, 1)

		ov_root = QWidget()
		ov_root.setObjectName("OverviewRoot")
		self.overview_scroll.setWidget(ov_root)

		root = QVBoxLayout(ov_root)
		root.setContentsMargins(18, 18, 18, 18)
		root.setSpacing(12)

		# --- Story card (first) ---
		self.story_card = QFrame()
		self.story_card.setObjectName("StoryCard")
		self.story_card.setAttribute(Qt.WA_StyledBackground, True)
		sc = QVBoxLayout(self.story_card)
		sc.setContentsMargins(16, 14, 16, 14)
		sc.setSpacing(10)

		self.story_title = QLabel("Story")
		self.story_title.setObjectName("StoryTitle")
		sc.addWidget(self.story_title)

		self.story_body = QLabel("NONE")
		self.story_body.setObjectName("StoryBody")
		self.story_body.setWordWrap(True)
		self.story_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
		sc.addWidget(self.story_body)

		root.addWidget(self.story_card, 0)

		# --- Flag submission panel (below story) ---
		self.flag_panel = QFrame()
		self.flag_panel.setObjectName("FlagPanel")
		self.flag_panel.setAttribute(Qt.WA_StyledBackground, True)
		fp = QVBoxLayout(self.flag_panel)
		
		# tighter top padding so "Submit Flag" sits higher (less dead space)
		fp.setContentsMargins(16, 8, 16, 14)
		fp.setSpacing(8)

		toprow = QHBoxLayout()
		toprow.setSpacing(10)
		fp.addLayout(toprow)

		self.flag_title = QLabel("Submit Flag")
		self.flag_title.setObjectName("FlagTitle")

		# Make the header bigger without relying on theme/QSS
		try:
			_ft = self.flag_title.font()
			_ft.setBold(True)
			_ft.setPointSize(max(_ft.pointSize() + 6, _ft.pointSize()))
			self.flag_title.setFont(_ft)
		except Exception:
			pass

		toprow.addWidget(self.flag_title, 1)

		# ---- Top-right: stacked pills (STATUS over DIFFICULTY, touching) ----
		self.flag_status_pill = QLabel("UNSOLVED")
		self.flag_status_pill.setObjectName("FlagStatusPill")
		self.flag_status_pill.setProperty("variant", "unsolved")

		self.flag_difficulty_pill = QLabel("—")
		self.flag_difficulty_pill.setObjectName("FlagDifficultyPill")
		self.flag_difficulty_pill.setProperty("variant", "neutral")

		pill_wrap = QFrame()
		pill_wrap.setObjectName("FlagPillsWrap")
		pill_wrap.setAttribute(Qt.WA_StyledBackground, True)

		pv = QVBoxLayout(pill_wrap)
		pv.setContentsMargins(0, 0, 0, 0)
		pv.setSpacing(0)  # IMPORTANT: pills touch

		# 🔒 Make this container hug its contents (prevents "stretch left")
		pv.setSizeConstraint(QLayout.SetFixedSize)

		pill_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
		self.flag_status_pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
		self.flag_difficulty_pill.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

		pv.addWidget(self.flag_status_pill, 0, Qt.AlignRight | Qt.AlignTop)
		pv.addWidget(self.flag_difficulty_pill, 0, Qt.AlignRight | Qt.AlignTop)

		toprow.addWidget(pill_wrap, 0, Qt.AlignRight | Qt.AlignTop)

		# Attempts only (status is now shown via the pill)
		self.flag_meta = QLabel("Attempts: —")
		self.flag_meta.setObjectName("Muted")
		self.flag_meta.setWordWrap(True)
		fp.addWidget(self.flag_meta)

		# ---- Flag body: controls only ----
		body = QHBoxLayout()
		body.setSpacing(14)
		fp.addLayout(body)

		controls = QFrame()
		controls.setObjectName("FlagControls")
		controls.setAttribute(Qt.WA_StyledBackground, True)
		cl = QHBoxLayout(controls)
		cl.setContentsMargins(0, 0, 0, 0)
		cl.setSpacing(12)

		self.flag_input = QLineEdit()
		self.flag_input.setObjectName("FlagInput")
		self.flag_input.setPlaceholderText("WEBVERSE{...}")
		self.flag_input.setClearButtonEnabled(False)
		self.flag_input.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
		self.flag_input.setFixedWidth(560)
		cl.addWidget(self.flag_input, 0, Qt.AlignLeft)

		self.flag_submit = QPushButton("Submit")
		self.flag_submit.setObjectName("PrimaryButton")
		self.flag_submit.setCursor(Qt.PointingHandCursor)
		self.flag_submit.setFixedHeight(44)
		self.flag_submit.setFixedWidth(170)
		cl.addWidget(self.flag_submit, 0, Qt.AlignLeft)

		body.addWidget(controls, 0, Qt.AlignTop)
		body.addStretch(1)

		self.flag_feedback = QLabel("")
		self.flag_feedback.setObjectName("FlagFeedback")
		self.flag_feedback.setWordWrap(True)
		fp.addWidget(self.flag_feedback)

		root.addWidget(self.flag_panel, 0)

		root.addStretch(1)

		self.tabs.addTab(self.overview, "Overview")

		# Info tab
		self.info = QWidget()
		inf = QVBoxLayout(self.info)
		inf.setContentsMargins(0, 0, 0, 0)
		inf.setSpacing(0)

		self.info_scroll = QScrollArea()
		self.info_scroll.setObjectName("InfoScroll")
		self.info_scroll.setWidgetResizable(True)
		self.info_scroll.setFrameShape(QFrame.NoFrame)
		inf.addWidget(self.info_scroll, 1)

		info_root = QWidget()
		info_root.setObjectName("InfoRoot")
		self.info_scroll.setWidget(info_root)

		info = QVBoxLayout(info_root)
		info.setContentsMargins(14, 14, 14, 14)
		info.setSpacing(12)

		# --- Top summary bar ---
		summary, s_l = _info_card("")
		summary.setObjectName("InfoSummaryCard")
		info.addWidget(summary, 0)

		sum_row = QHBoxLayout()
		sum_row.setSpacing(10)

		self.info_title = QLabel("Lab Details")
		self.info_title.setObjectName("InfoSummaryTitle")
		sum_row.addWidget(self.info_title, 1)

		self.info_pill = QLabel("—")
		self.info_pill.setObjectName("InfoPill")
		sum_row.addWidget(self.info_pill, 0, Qt.AlignRight)

		s_l.addLayout(sum_row)
		s_l.addWidget(_info_divider())

		self.info_sub = QLabel("—")
		self.info_sub.setObjectName("InfoSummarySub")
		self.info_sub.setTextInteractionFlags(Qt.TextSelectableByMouse)
		s_l.addWidget(self.info_sub)

		# --- Two-column cards ---
		cols = QHBoxLayout()
		cols.setSpacing(12)
		info.addLayout(cols, 0)

		# Left: Details card
		details_card, d = _info_card("Details")
		cols.addWidget(details_card, 3)

		self._info_rows = {}

		r, v, right = _kv_row("Name")
		d.addWidget(r); self._info_rows["name"] = v

		r, v, right = _kv_row("ID", mono=True)
		d.addWidget(r); self._info_rows["id"] = v
		btn = _icon_btn("InfoCopyBtn", "Copy ID", _make_copy_icon(QColor(245, 197, 66), 18))
		right.addWidget(btn)
		btn.clicked.connect(lambda: self._info_copy("id"))

		r, v, right = _kv_row("Difficulty")
		d.addWidget(r); self._info_rows["difficulty"] = v

		r, v, right = _kv_row("Path", mono=True)
		d.addWidget(r); self._info_rows["path"] = v
		btn = _icon_btn("InfoCopyBtn", "Copy Path", _make_copy_icon(QColor(245, 197, 66), 18))
		right.addWidget(btn)
		btn.clicked.connect(lambda: self._info_copy("path"))

		r, v, right = _kv_row("Compose", mono=True)
		d.addWidget(r); self._info_rows["compose"] = v
		btn = _icon_btn("InfoCopyBtn", "Copy Compose File", _make_copy_icon(QColor(245, 197, 66), 18))
		right.addWidget(btn)
		btn.clicked.connect(lambda: self._info_copy("compose"))

		r, v, right = _kv_row("Entrypoint", mono=True)
		d.addWidget(r); self._info_rows["entrypoint"] = v

		copy_ep = _icon_btn("InfoCopyBtn", "Copy Entrypoint", _make_copy_icon(QColor(245, 197, 66), 18))
		right.addWidget(copy_ep)
		copy_ep.clicked.connect(lambda: self._info_copy("entrypoint"))

		open_ep = _icon_btn("InfoOpenBtn", "Open Entrypoint", self.style().standardIcon(QStyle.SP_DialogOpenButton))
		right.addWidget(open_ep)
		open_ep.clicked.connect(self._info_open_entrypoint)

		# Right: Quick actions card
		actions_card, a = _info_card("Quick Actions")
		cols.addWidget(actions_card, 2)

		self.info_action_open_folder = QPushButton("Open Lab Folder")
		self.info_action_open_folder.setObjectName("GhostButton")
		self.info_action_open_folder.setCursor(Qt.PointingHandCursor)
		a.addWidget(self.info_action_open_folder)

		self.info_action_open_compose = QPushButton("Open docker-compose.yml")
		self.info_action_open_compose.setObjectName("GhostButton")
		self.info_action_open_compose.setCursor(Qt.PointingHandCursor)
		a.addWidget(self.info_action_open_compose)

		self.info_action_copy_all = QPushButton("Copy All Details")
		self.info_action_copy_all.setObjectName("PrimaryButton")
		self.info_action_copy_all.setCursor(Qt.PointingHandCursor)
		a.addWidget(self.info_action_copy_all)

		a.addStretch(1)

		self.info_action_open_folder.clicked.connect(self._info_open_folder)
		self.info_action_open_compose.clicked.connect(self._info_open_compose)
		self.info_action_copy_all.clicked.connect(self._info_copy_all)

		# --- Description card (full width) ---
		desc_card, dc = _info_card("Description")
		info.addWidget(desc_card, 0)

		self.info_desc = QLabel("—")
		self.info_desc.setObjectName("InfoDesc")
		self.info_desc.setWordWrap(True)
		self.info_desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
		dc.addWidget(self.info_desc)

		info.addStretch(1)

		self.tabs.addTab(self.info, "Info")

		# Logs tab
		self.logs_tab = QWidget()
		lt = QVBoxLayout(self.logs_tab)
		lt.setContentsMargins(0, 0, 0, 0)
		lt.setSpacing(10)

		self.logs = QTextEdit()
		self.logs.setObjectName("LogsBox")
		self.logs.setReadOnly(True)
		self.logs.setPlaceholderText("Compose logs will appear here…")
		self.logs.setProperty("noAmberFocus", True)
		self.logs.setFocusPolicy(Qt.NoFocus)
		lt.addWidget(self.logs, 1)

		self.tabs.addTab(self.logs_tab, "Logs")

		# ---- Tab-corner action (prevents overlap with tab headers) ----
		self._logs_tab_index = self.tabs.indexOf(self.logs_tab)

		self.btn_refresh_logs = QPushButton("Refresh Logs")
		self.btn_refresh_logs.setObjectName("GhostButton")
		self.btn_refresh_logs.setCursor(Qt.PointingHandCursor)
		self.btn_refresh_logs.setFixedHeight(40)
		self.btn_refresh_logs.setMinimumWidth(132)  # ensure text isn't clipped
		self.btn_refresh_logs.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

		_corner = QFrame()
		_corner.setObjectName("TabsCorner")
		_corner.setAttribute(Qt.WA_StyledBackground, True)
		_cl = QHBoxLayout(_corner)
		_cl.setContentsMargins(0, 0, 8, 0)
		_cl.setSpacing(0)
		_cl.addWidget(self.btn_refresh_logs, 0, Qt.AlignVCenter)

		self.tabs.setCornerWidget(_corner, Qt.TopRightCorner)
		_corner.setVisible(False)  # only visible on Logs tab
		self._tabs_corner = _corner

		# Wire actions
		self.btn_refresh_logs.clicked.connect(self._on_refresh_logs)
		self.flag_submit.clicked.connect(self._on_submit_flag)
		self.flag_input.returnPressed.connect(self._on_submit_flag)

		# -------------------------
		# ConnBar buttons
		# -------------------------
		self.conn.btn_start.clicked.connect(self._on_start)
		self.conn.btn_stop.clicked.connect(self._on_stop)
		self.conn.btn_reset.clicked.connect(self._on_reset)

		# Entrypoint behavior:
		# - copy icon always copies
		# - clicking the *actual URL text* copies (NOT the empty label area, NOT the whole bar)
		# - no double-click open
		self.conn.copy_btn.clicked.connect(self._endpoint_copy)
		self.conn._on_entrypoint_text_clicked = self._endpoint_copy

		# Show corner action only when Logs tab is selected
		self.tabs.currentChanged.connect(self._on_tab_changed)

		self._set_actions_enabled(False)

	def _is_running(self, lab_id: str | None) -> bool:
		try:
			return bool(lab_id) and (get_running_lab() == lab_id)
		except Exception:
			return False

	def _compute_flag_status(self, solved_at, lab_id: str | None) -> str:
		"""
		We want the pill to reflect *current* state:
		- SOLVED if solved_at exists
		- ACTIVE if the lab is currently running
		- otherwise UNSOLVED
		"""
		if solved_at:
			return "Solved"
		if self._is_running(lab_id):
			return "Active"
		return "Unsolved"

	def _sync_flag_pills_width(self):
		"""
		Force STATUS and DIFFICULTY pills to be the exact same width,
		large enough for whatever text is currently inside either pill.
		"""
		if not hasattr(self, "flag_status_pill") or not hasattr(self, "flag_difficulty_pill"):
			return

		pills = (self.flag_status_pill, self.flag_difficulty_pill)

		# IMPORTANT:
		# If these labels already have a fixed width, Qt's sizeHint() can be >= that width.
		# If we then add padding (+18) again, they "creep" wider on every refresh.
		# So: temporarily remove width constraints, measure, then re-apply fixed width.
		for p in pills:
			p.setMinimumWidth(0)
			p.setMaximumWidth(16777215)
			p.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
			p.adjustSize()

		w = max(p.sizeHint().width() for p in pills) + 18

		for p in pills:
			p.setFixedWidth(w)

	def _set_flag_status(self, status: str, attempts: int):
		"""
		Updates the STATUS pill and Attempts line.
		status: "Solved" | "Active" | "Unsolved"
		"""
		if not hasattr(self, "flag_status_pill"):
			return

		s = (status or "").strip().lower()
		if s == "solved":
			self.flag_status_pill.setText("SOLVED")
			self.flag_status_pill.setProperty("variant", "solved")
		elif s == "active":
			self.flag_status_pill.setText("ACTIVE")
			self.flag_status_pill.setProperty("variant", "active")
		else:
			self.flag_status_pill.setText("UNSOLVED")
			self.flag_status_pill.setProperty("variant", "unsolved")

		try:
			self.flag_meta.setText(f"Attempts: {int(attempts)}")
		except Exception:
			self.flag_meta.setText("Attempts: —")

		self.flag_status_pill.style().unpolish(self.flag_status_pill)
		self.flag_status_pill.style().polish(self.flag_status_pill)
		self.flag_status_pill.update()

		self._sync_flag_pills_width()

	def _set_flag_difficulty(self, difficulty: str):
		if not hasattr(self, "flag_difficulty_pill"):
			return

		d = (difficulty or "").strip().lower()
		txt = (difficulty or "Unknown").strip().upper()

		variant = "neutral"
		if d in ("easy",):
			variant = "easy"
		elif d in ("medium",):
			variant = "medium"
		elif d in ("hard",):
			variant = "hard"
		elif d in ("master",):
			variant = "master"

		self.flag_difficulty_pill.setText(txt)
		self.flag_difficulty_pill.setProperty("variant", variant)

		self.flag_difficulty_pill.style().unpolish(self.flag_difficulty_pill)
		self.flag_difficulty_pill.style().polish(self.flag_difficulty_pill)
		self.flag_difficulty_pill.update()

		self._sync_flag_pills_width()

	def _update_flag_lock(self, solved: bool):
		"""
		Locks flag submission when solved.
		"""

		# Status pill is shown in the top-right of the flag panel.
		if hasattr(self, "flag_status_pill"):
			if solved:
				self.flag_status_pill.setText("SOLVED")
				self.flag_status_pill.setProperty("variant", "solved")
			else:
				# Keep whatever the last computed status was (unsolved/active).
				# If nothing has set it yet, default to UNSOLVED.
				cur = (self.flag_status_pill.text() or "").strip()
				if not cur or cur == "—" or cur.upper() == "SOLVED":
					self.flag_status_pill.setText("UNSOLVED")
					self.flag_status_pill.setProperty("variant", "unsolved")

			self.flag_status_pill.style().unpolish(self.flag_status_pill)
			self.flag_status_pill.style().polish(self.flag_status_pill)
			self.flag_status_pill.update()

		# Clear any old styling variants
		self.flag_panel.setProperty("variant", "")
		self.flag_panel.style().unpolish(self.flag_panel)
		self.flag_panel.style().polish(self.flag_panel)
		self.flag_panel.update()

		self.flag_input.setProperty("variant", "")
		self.flag_input.style().unpolish(self.flag_input)
		self.flag_input.style().polish(self.flag_input)
		self.flag_input.update()

		self.flag_input.setEnabled(not solved)
		self.flag_submit.setEnabled(not solved)
		if solved:
			self.flag_input.setPlaceholderText("")
			self.flag_input.setText("Lab has been solved")
		else:
			if self.flag_input.text().strip() == "Lab has been solved":
				self.flag_input.setText("")
			self.flag_input.setPlaceholderText("WEBVERSE{...}")

		self._sync_flag_pills_width()

	# ---------- Info Tab helpers ----------
	def _info_set(self, key: str, value: str):
		if not hasattr(self, "_info_rows") or key not in self._info_rows:
			return
		self._info_rows[key].setText(value if (value and str(value).strip()) else "—")

	def _info_get(self, key: str) -> str:
		if not hasattr(self, "_info_rows") or key not in self._info_rows:
			return ""
		txt = self._info_rows[key].text() or ""
		return "" if txt.strip() == "—" else txt.strip()

	def _info_copy(self, key: str):
		val = self._info_get(key)
		if not val:
			self._toast("Nothing to copy", "This field is empty.", variant="error", ms=1400)
			return
		QApplication.clipboard().setText(val)
		self._toast("Copied", f"{key.title()} copied.", variant="success", ms=1200)

	def _info_copy_all(self):
		parts = []
		for k, label in (
			("Name", "name"),
			("ID", "id"),
			("Difficulty", "difficulty"),
			("Path", "path"),
			("Compose", "compose"),
			("Entrypoint", "entrypoint"),
		):
			v = self._info_get(label)
			if v:
				parts.append(f"{k}: {v}")

		desc = (self.info_desc.text() or "").strip()
		if desc and desc != "—":
			parts.append("")
			parts.append("Description:")
			parts.append(desc)

		blob = "\n".join(parts).strip()
		if not blob:
			self._toast("Nothing to copy", "No info available.", variant="error", ms=1400)
			return

		QApplication.clipboard().setText(blob)
		self._toast("Copied", "All details copied.", variant="success", ms=1300)

	def _info_open_entrypoint(self):
		url = self._info_get("entrypoint")
		if not url:
			self._toast("No entrypoint", "This lab has no entrypoint URL.", variant="error", ms=1600)
			return
		QDesktopServices.openUrl(QUrl(url))

	def _info_open_folder(self):
		if not self._lab:
			return
		try:
			p = str(self._lab.path)
			QDesktopServices.openUrl(QUrl.fromLocalFile(p))
		except Exception as e:
			self._toast("Failed", str(e), variant="error", ms=1800)

	def _info_open_compose(self):
		if not self._lab:
			return
		try:
			compose_name = getattr(self._lab, "compose_file", "docker-compose.yml") or "docker-compose.yml"
			compose_path = os.path.join(str(self._lab.path), compose_name)
			QDesktopServices.openUrl(QUrl.fromLocalFile(compose_path))
		except Exception as e:
			self._toast("Failed", str(e), variant="error", ms=1800)

	# ---------- toast helper ----------
	def _toast(self, title: str, body: str, variant: str = "success", ms: int = 1700):
		"""
		Prefer a global ToastHost owned by the MainWindow (if present),
		otherwise fall back to a host attached to our window.
		"""
		mw = self.window()
		if not mw:
			return

		# Preferred: MainWindow has toast_host or show_toast
		if hasattr(mw, "show_toast") and callable(getattr(mw, "show_toast")):
			try:
				mw.show_toast(title, body, variant=variant, ms=ms)
				return
			except Exception:
				pass

		host = getattr(mw, "toast_host", None)
		if host and hasattr(host, "show_toast"):
			host.show_toast(title, body, variant=variant, ms=ms)
			return

		# Last resort: create one lazily (kept alive by mw attr)
		if not hasattr(mw, "_fallback_toast_host"):
			mw._fallback_toast_host = ToastHost(mw)
		mw._fallback_toast_host.show_toast(title, body, variant=variant, ms=ms)

	def set_nav_enabled(self, back: bool, forward: bool) -> None:
		self.btn_back.setEnabled(bool(back))
		self.btn_forward.setEnabled(bool(forward))

	def set_lab(self, lab):
		self._lab = lab
		self.flag_input.clear()
		self.flag_feedback.setText("")

		# Story (lab.yml: story)
		story = (getattr(lab, "story", "") or "").strip()
		self.story_body.setText(story if story else "NONE")

		# breadcrumbs
		self.crumb_current.setText(getattr(lab, 'name', '—') or '—')

		self.lab_name.setText(lab.name)

		size = 72

		img = None
		try:
			imgp = getattr(lab, "image_path", None)
			if callable(imgp):
				p = imgp()
				img = str(p) if p else None
		except Exception:
			img = None

		if img:
			ico = lab_badge_icon(lab.name, getattr(lab, "difficulty", None), img, size)
		else:
			ico = lab_circle_icon(lab.name, getattr(lab, "difficulty", None), size)
		self.avatar.setPixmap(ico.pixmap(size, size))

		# entrypoint
		url = getattr(lab, "url", "") or ""
		if not url:
			# common names in your Lab model
			url = getattr(lab, "entrypoint", "") or getattr(lab, "entry", "") or ""
		resolved_url = self.conn.set_url(url)

		# reset UI
		self.logs.clear()

		# Info tab (gorgeous structured)
		self._info_set("name", lab.name or "—")
		self._info_set("id", lab.id or "—")
		self._info_set("difficulty", (lab.difficulty or "Unknown").title())
		self._info_set("path", str(lab.path))
		self._info_set("compose", getattr(lab, "compose_file", "docker-compose.yml") or "docker-compose.yml")

		ep = resolved_url or ""
		self._info_set("entrypoint", ep if ep else "—")

		bits = []
		if lab.id:
			bits.append(lab.id)
		if getattr(lab, "difficulty", None):
			bits.append((lab.difficulty or "").title())
		self.info_sub.setText(" • ".join(bits) if bits else "—")

		pill = (lab.difficulty or "Unknown").upper()
		self.info_pill.setText(pill)

		desc = (getattr(lab, "description", "") or "").strip()
		self.info_desc.setText(desc if desc else "—")

		# progress info
		prog = self.state.progress_map().get(lab.id, {}) if hasattr(self.state, "progress_map") else {}
		attempts = int(prog.get("attempts") or 0)
		started_at = prog.get("started_at")
		solved_at = prog.get("solved_at")

		status = self._compute_flag_status(solved_at, lab.id)
		self._set_flag_status(status, attempts)
		self._set_flag_difficulty(getattr(lab, "difficulty", "") or "Unknown")
		self._update_flag_lock(bool(solved_at))
		self._sync_flag_pills_width()

		# running badge from runtime
		running = self._is_running(lab.id)
		self._set_op_state("running" if running else "stopped")

		self._set_actions_enabled(True)

	# -------- threaded docker ops --------
	def _run_docker(self, title: str, fn, *args, on_done=None, **kwargs):
		# Be defensive: older installs / partial refactors may not have _thread yet.
		thr = getattr(self, "_thread", None)
		if thr is not None:
			self._append_activity("Busy: wait for current operation to finish.")
			return

		# Ensure attributes exist even if __init__ didn't set them for some reason.
		if not hasattr(self, "_thread"):
			self._thread = None
		if not hasattr(self, "_worker"):
			self._worker = None

		self._append_activity(title)

		self._thread = QThread()
		self._worker = _DockerWorker(fn, *args, **kwargs)
		self._worker.moveToThread(self._thread)

		self._thread.started.connect(self._worker.run)

		def _finished(ok: bool, msg: str):
			try:
				if on_done:
					on_done(ok, msg)
			finally:
				self._thread.quit()
				self._thread.wait(2000)
				self._thread = None
				self._worker = None

		self._worker.finished.connect(_finished)
		self._thread.start()

	# -------- state visuals --------
	def _set_op_state(self, state: str):
		self._op_state = state
		self.conn.set_state(state)

	def _on_tab_changed(self, idx: int):
		try:
			self._tabs_corner.setVisible(idx == self._logs_tab_index)
		except Exception:
			pass

	def _set_actions_enabled(self, enabled: bool):
		self.conn.setEnabled(bool(enabled))
		self.btn_refresh_logs.setEnabled(bool(enabled))

	def _append_activity(self, line: str):
		ts = time.strftime("%H:%M:%S")
		msg = f"[{ts}] {line}"
		# Always keep an in-memory activity feed (prevents crashes if UI widget is missing)
		try:
			self._activity_lines.append(msg)
		except Exception:
			pass

		# Optional UI sink (only if it exists)
		w = getattr(self, "activity", None)
		if w is not None and hasattr(w, "append"):
			try:
				w.append(msg)
				return
			except Exception:
				pass

	def _fmt_uptime(self, seconds: int) -> str:
		if seconds <= 0:
			return "—"
		d = seconds // 86400
		h = (seconds % 86400) // 3600
		m = (seconds % 3600) // 60
		s = seconds % 60
		if d > 0:
			return f"{d}d {h:02d}h {m:02d}m"
		if h > 0:
			return f"{h}h {m:02d}m {s:02d}s"
		if m > 0:
			return f"{m}m {s:02d}s"
		return f"{s}s"

	def _port_available(self, port: int) -> bool:
		"""
		Best-effort local port availability check.
		Returns True if we can bind to the port on 0.0.0.0, else False.
		"""
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			try:
				# Avoid TIME_WAIT false negatives on some platforms
				s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
				s.bind(("0.0.0.0", int(port)))
				return True
			finally:
				try:
					s.close()
				except Exception:
					pass
		except Exception:
			return False

	def _extract_host_ports_from_compose(self, compose_text: str) -> list[int]:
		"""
		Extract host ports from docker-compose.yml text (common patterns).
		We only care about ports that will actually bind on the host.
		"""
		if not compose_text:
			return []

		txt = compose_text
		ports: set[int] = set()

		# Pattern A: long form mapping with 'published: 8080'
		for m in re.finditer(r"(?im)^\s*published\s*:\s*(\d+)\s*$", txt):
			try:
				ports.add(int(m.group(1)))
			except Exception:
				pass

		# Pattern B: short form strings in ports list:
		# - "8080:80"
		# - "127.0.0.1:8080:80"
		# - 8080:80
		# (We ignore bare "80" because that doesn't bind a host port.)
		for line in txt.splitlines():
			l = line.strip()
			if not l.startswith("-"):
				continue

			# strip list marker and surrounding quotes
			val = l[1:].strip().strip('"').strip("'")

			# remove trailing comments
			if "#" in val:
				val = val.split("#", 1)[0].strip()

			# Only consider mappings with at least one colon
			if ":" not in val:
				continue

			parts = [p.strip() for p in val.split(":") if p.strip()]

			# Cases:
			# host:container  -> ["8080","80"] => host is parts[0]
			# ip:host:container -> ["127.0.0.1","8080","80"] => host is parts[1]
			# (If weird extras exist, we still try best-effort.)
			host_part = None
			if len(parts) == 2 and parts[0].isdigit():
				host_part = parts[0]
			elif len(parts) >= 3 and parts[1].isdigit():
				host_part = parts[1]

			if host_part:
				try:
					ports.add(int(host_part))
				except Exception:
					pass

		return sorted(ports)

	def _get_lab_host_ports(self, lab) -> list[int]:
		"""
		Load the lab's compose file and return host ports it intends to bind.
		"""
		try:
			compose_name = getattr(lab, "compose_file", "docker-compose.yml") or "docker-compose.yml"
			compose_path = Path(str(lab.path)) / compose_name
			if not compose_path.exists():
				return []
			txt = compose_path.read_text(encoding="utf-8", errors="ignore")
			return self._extract_host_ports_from_compose(txt)
		except Exception:
			return []

	def _tick_uptime(self):
		# Uses progress.started_at if available; otherwise shows —
		if not self._lab or not hasattr(self, "_k_uptime_v"):
			return
		try:
			prog = self.state.progress_map().get(self._lab.id, {}) if hasattr(self.state, "progress_map") else {}
			started_at = prog.get("started_at")
			if not started_at:
				self._k_uptime_v.setText("—")
				return

			# Accept either unix seconds or iso-ish string
			start_ts = None
			if isinstance(started_at, (int, float)):
				start_ts = int(started_at)
			elif isinstance(started_at, str) and started_at.strip():
				# try common ISO formats
				try:
					dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
					start_ts = int(dt.timestamp())
				except Exception:
					start_ts = None

			if not start_ts:
				self._k_uptime_v.setText("—")
				return

			now = int(time.time())
			self._k_uptime_v.setText(self._fmt_uptime(max(0, now - start_ts)))
		except Exception:
			self._k_uptime_v.setText("—")

	# -------- actions --------
	def _on_start(self):
		if not self._lab:
			return
		lab = self._lab

		# ✅ Prevent multiple labs running at once
		running_id = get_running_lab()
		if running_id and running_id != lab.id:
			self.flag_feedback.setProperty("variant", "error")
			self.flag_feedback.style().unpolish(self.flag_feedback)
			self.flag_feedback.style().polish(self.flag_feedback)
			self.flag_feedback.setText("❌ You can only launch one lab at a time.")

			self._append_activity(f"❌ Launch blocked: {running_id} is already running.")

			self._toast("Blocked", "You can only launch one lab at a time.", variant="error", ms=2000)
			return

		# ✅ Pre-check host ports before running docker compose
		try:
			needed_ports = self._get_lab_host_ports(lab)
			if needed_ports:
				busy = [p for p in needed_ports if not self._port_available(p)]
				if busy:
					plist = ", ".join(str(p) for p in busy[:6])
					more = ""
					if len(busy) > 6:
						more = f" (+{len(busy) - 6} more)"
					self._toast(
						"Port in use",
						f"This lab needs host port(s) {plist}{more}, but they're already in use. Stop the service using them, then try again.",
						variant="error",
						ms=2800,
					)
					self._append_activity(f"❌ Launch blocked: port(s) in use: {', '.join(str(p) for p in busy)}")
					return
		except Exception:
			# Never block launch due to precheck errors
			pass

		self._set_op_state("starting")

		def done(ok: bool, msg: str):
			if ok:
				# ✅ Only mark "started" if the compose up actually succeeded.
				# started_at becomes the most recent successful start time.
				progress_db.mark_started(lab.id)

				self.state.set_running_lab_id(lab.id)
				self._append_activity("✅ Lab started.")
				self._set_op_state("running")

				# status pill should reflect running state
				try:
					self._set_flag_status("Active", int((self.state.progress_map().get(lab.id, {}) or {}).get("attempts") or 0))
				except Exception:
					self._set_flag_status("Active", 0)
			else:
				self._append_activity("❌ Failed to start lab.")
				if msg:
					self._append_activity(msg)
				self._set_op_state("stopped")

		self._run_docker("Starting lab…", docker_ops.compose_up, str(lab.path), lab.compose_file, on_done=done)

	def _on_stop(self):
		if not self._lab:
			return
		lab = self._lab

		self._set_op_state("stopping")

		def done(ok: bool, msg: str):
			if ok:
				self.state.set_running_lab_id(None)
				self._append_activity("✅ Lab stopped.")

				# ✅ Attempts mean: started → stopped without solving.
				# Only increment if the lab is NOT solved.
				try:
					prog = self.state.progress_map().get(lab.id, {}) if hasattr(self.state, "progress_map") else {}
					solved_at = prog.get("solved_at")
					if not solved_at:
						progress_db.mark_attempt(lab.id)
				except Exception:
					# attempts are non-critical; never break stop UX
					pass
			else:
				self._append_activity("❌ Failed to stop lab.")
				if msg:
					self._append_activity(msg)
			self._set_op_state("stopped")

			# status pill should reflect not-running (unless solved)
			try:
				prog = self.state.progress_map().get(lab.id, {}) if hasattr(self.state, "progress_map") else {}
				self._set_flag_status(self._compute_flag_status(prog.get("solved_at"), lab.id), int(prog.get("attempts") or 0))
				self._update_flag_lock(bool(prog.get("solved_at")))
			except Exception:
				pass

		self._run_docker("Stopping lab…", docker_ops.compose_down, str(lab.path), lab.compose_file, on_done=done)

	def _on_reset(self):
		if not self._lab:
			return
		lab = self._lab

		self._set_op_state("resetting")

		def done(ok: bool, msg: str):
			if ok:
				self._append_activity("✅ Lab reset and restarted.")
				# ✅ keep the app's running state in sync
				try:
					set_running_lab(lab.id)  # core.runtime
				except Exception:
					pass
				try:
					self.state.set_running_lab_id(lab.id)  # AppState
				except Exception:
					pass
				self._set_op_state("running")

				# status pill should reflect running state
				try:
					prog = self.state.progress_map().get(lab.id, {}) if hasattr(self.state, "progress_map") else {}
					self._set_flag_status("Active", int(prog.get("attempts") or 0))
				except Exception:
					self._set_flag_status("Active", 0)
			else:
				self._append_activity("❌ Failed to reset lab.")
				if msg:
					self._append_activity(msg)
				# If reset failed, lab is not guaranteed running
				try:
					set_running_lab(None)
				except Exception:
					pass
				try:
					self.state.set_running_lab_id(None)
				except Exception:
					pass
				self._set_op_state("stopped")

				# reflect not-running
				try:
					prog = self.state.progress_map().get(lab.id, {}) if hasattr(self.state, "progress_map") else {}
					self._set_flag_status(self._compute_flag_status(prog.get("solved_at"), lab.id), int(prog.get("attempts") or 0))
					self._update_flag_lock(bool(prog.get("solved_at")))
				except Exception:
					pass

		self._run_docker("Resetting lab…", docker_ops.compose_reset, str(lab.path), lab.compose_file, on_done=done)

	def _on_refresh_logs(self):
		if not self._lab:
			return
		lab = self._lab

		def done(ok: bool, msg: str):
			# Put the compose logs output into the Logs tab
			if ok:
				self.logs.setPlainText(msg)

		self._run_docker("Fetching logs…", docker_ops.compose_logs, str(lab.path), lab.compose_file, 240, on_done=done)

	def _on_submit_flag(self):
		if not self._lab:
			return

		# If already solved, block resubmits (also visually locked via _update_flag_lock)
		try:
			prog = self.state.progress_map().get(self._lab.id, {}) if hasattr(self.state, "progress_map") else {}
			if prog.get("solved_at"):
				self._toast("Locked", "This lab is already solved.", variant="error", ms=1600)
				return
		except Exception:
			pass

		flag = (self.flag_input.text() or "").strip()
		if not flag:
			self.flag_feedback.setText("Enter a flag first.")
			return

		lab = self._lab

		ok = False
		msg = ""

		# Try to use whatever the app already exposes, without hard-coupling.
		try:
			if hasattr(self.state, "submit_flag") and callable(getattr(self.state, "submit_flag")):
				res = self.state.submit_flag(lab.id, flag)
				if isinstance(res, tuple) and len(res) >= 1:
					ok = bool(res[0])
					msg = str(res[1]) if len(res) > 1 and res[1] is not None else ""
				else:
					ok = bool(res)

			elif hasattr(self.state, "check_flag") and callable(getattr(self.state, "check_flag")):
				res = self.state.check_flag(lab.id, flag)
				if isinstance(res, tuple) and len(res) >= 1:
					ok = bool(res[0])
					msg = str(res[1]) if len(res) > 1 and res[1] is not None else ""
				else:
					ok = bool(res)

			else:
				# fallback: compare against lab.flag if present
				expected = getattr(lab, "flag", None)
				if isinstance(expected, str) and expected:
					ok = (flag == expected.strip())
				else:
					msg = "No flag validator is wired yet."
					ok = False
		except Exception as e:
			ok = False
			msg = str(e)

		if ok:
			self.flag_feedback.setText("✅ Correct flag.")
			self._append_activity("🏁 Flag accepted.")
			self.flag_input.clear()

			# lock UI immediately; refresh below will keep it consistent
			self._update_flag_lock(True)

			self._toast("Success", "Flag accepted.", variant="success", ms=1600)
		else:
			self.flag_feedback.setText("❌ Incorrect flag." + (f" ({msg})" if msg else ""))
			self._append_activity("❌ Incorrect flag submitted.")

			self._toast("Nope", "Incorrect flag.", variant="error", ms=1600)

		# refresh meta (attempts/status) if your state tracks it
		try:
			prog = self.state.progress_map().get(lab.id, {}) if hasattr(self.state, "progress_map") else {}
			attempts = int(prog.get("attempts") or 0)
			started_at = prog.get("started_at")
			solved_at = prog.get("solved_at")
			self._set_flag_status(self._compute_flag_status(solved_at, lab.id), attempts)
			self._update_flag_lock(bool(solved_at))
			self._sync_flag_pills_width()
		except Exception:
			pass

	# Entrypoint tile actions
	def _endpoint_copy(self, *_args):
		url = self.conn.url()
		if not url:
			self._append_activity("❌ No entrypoint URL configured for this lab.")
			return

		QApplication.clipboard().setText(url)

		self._toast("Success", "Entrypoint copied to clipboard successfully.", variant="success", ms=1400)
	
	def _endpoint_double_click(self, _ev):
		url = self.conn.url()
		if not url:
			self._append_activity("❌ No entrypoint URL configured for this lab.")
			return
		QDesktopServices.openUrl(QUrl(url))
		self._append_activity(f"Opened: {url}")