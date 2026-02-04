from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
	QWidget,
	QVBoxLayout,
	QHBoxLayout,
	QFrame,
	QLabel,
	QPushButton,
	QScrollArea,
	QSizePolicy,
	QButtonGroup,
	QTableWidget,
	QTableWidgetItem,
)

from webverse.core.runtime import get_running_lab
from webverse.core.xp import base_xp_for_difficulty
from webverse.core.progress_db import get_progress_map
from webverse.gui.util_avatar import lab_badge_icon, lab_circle_icon
from webverse.core.ranks import rank_for_xp, total_xp as _total_xp, solved_count as _solved_count, completion_percent as _completion_percent, solve_streak_days as _solve_streak_days

class ProgressView(QWidget):
	# MainWindow will connect this to navigate into the lab detail page
	lab_selected = pyqtSignal(str)

	def __init__(self, state, parent=None):
		super().__init__(parent)
		self.state = state
		self._filter_mode = "all"  # all | solved | active | unsolved

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(12)

		surface = QFrame()
		surface.setObjectName("ContentSurface")
		surface.setAttribute(Qt.WA_StyledBackground, True)

		layout = QVBoxLayout(surface)
		layout.setContentsMargins(22, 18, 22, 18)
		layout.setSpacing(14)

		title = QLabel("Progress")
		title.setObjectName("H1")
		layout.addWidget(title)

		subtitle = QLabel("Ranks, XP, and your mission log. Stored locally in progress.db.")
		subtitle.setObjectName("Muted")
		layout.addWidget(subtitle)

		# ---- Top cards (Rank + Track) ----
		top = QHBoxLayout()
		top.setSpacing(12)
		layout.addLayout(top)

		self.player = QFrame()
		self.player.setObjectName("PlayerCard")
		self.player.setAttribute(Qt.WA_StyledBackground, True)
		self.player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		top.addWidget(self.player, 1)

		pl = QHBoxLayout(self.player)
		pl.setContentsMargins(14, 14, 14, 14)
		pl.setSpacing(12)

		self.rank_icon = QLabel()
		self.rank_icon.setFixedSize(54, 54)
		pl.addWidget(self.rank_icon, 0, Qt.AlignTop)

		col = QVBoxLayout()
		col.setSpacing(6)
		pl.addLayout(col, 1)

		self.rank_name = QLabel("Bronze I")
		self.rank_name.setObjectName("RankName")
		col.addWidget(self.rank_name)

		self.rank_sub = QLabel("0 XP")
		self.rank_sub.setObjectName("Muted")
		col.addWidget(self.rank_sub)

		self.xp_bar = _XPBar()
		self.xp_bar.setFixedHeight(10)
		col.addWidget(self.xp_bar)

		self.rank_next = QLabel("Next rank: —")
		self.rank_next.setObjectName("Subtle")
		col.addWidget(self.rank_next)

		self.track = QFrame()
		self.track.setObjectName("RankTrack")
		self.track.setAttribute(Qt.WA_StyledBackground, True)
		self.track.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		top.addWidget(self.track, 1)

		tl = QVBoxLayout(self.track)
		tl.setContentsMargins(14, 14, 14, 14)
		tl.setSpacing(8)

		self.track_title = QLabel("Season Track")
		self.track_title.setObjectName("H2")
		tl.addWidget(self.track_title)

		self.track_hint = QLabel("Solve higher difficulties for bigger XP. Maintain streaks and climb ranks.")
		self.track_hint.setObjectName("Muted")
		self.track_hint.setWordWrap(True)
		tl.addWidget(self.track_hint)

		# ---- Stats row ----
		stats = QHBoxLayout()
		stats.setSpacing(12)
		layout.addLayout(stats)

		self.stat_solves = self._stat_card("Solves", "0")
		self.stat_streak = self._stat_card("Solve Streak", "0")
		self.stat_completion = self._stat_card("Completion", "0%")
		self.stat_total = self._stat_card("Total Labs", "0")
		for w in (self.stat_solves, self.stat_streak, self.stat_completion, self.stat_total):
			stats.addWidget(w, 1)

		# ---- Missions header + filter pills ----
		filters = QHBoxLayout()
		filters.setSpacing(10)
		layout.addLayout(filters)

		filters_title = QLabel("Missions")
		filters_title.setObjectName("H2")
		filters.addWidget(filters_title, 0, Qt.AlignVCenter)
		filters.addStretch(1)

		self._filter_group = QButtonGroup(self)
		self._filter_group.setExclusive(True)

		self.btn_all = self._filter_btn("All", "all")
		self.btn_solved = self._filter_btn("Solved", "solved")
		self.btn_active = self._filter_btn("Active", "active")
		self.btn_unsolved = self._filter_btn("Unsolved", "unsolved")

		for b in (self.btn_all, self.btn_solved, self.btn_active, self.btn_unsolved):
			filters.addWidget(b, 0, Qt.AlignVCenter)

		self.btn_all.setChecked(True)

		# ---- Mission list ----
		self.scroll = QScrollArea()
		self.scroll.setWidgetResizable(True)
		self.scroll.setFrameShape(QFrame.NoFrame)
		self.scroll.setAttribute(Qt.WA_StyledBackground, True)
		self.scroll.setStyleSheet("background: transparent;")
		self.scroll.viewport().setStyleSheet("background: transparent;")
		layout.addWidget(self.scroll, 1)

		self.list_host = QWidget()
		self.list_host.setAttribute(Qt.WA_StyledBackground, True)
		self.list_host.setStyleSheet("background: transparent;")
		self.scroll.setWidget(self.list_host)

		self.list_layout = QVBoxLayout(self.list_host)
		self.list_layout.setContentsMargins(0, 0, 0, 0)
		self.list_layout.setSpacing(10)

		# Empty state (shown when no rows match filter)
		self.empty_state = QFrame()
		self.empty_state.setObjectName("EmptyState")
		self.empty_state.setAttribute(Qt.WA_StyledBackground, True)

		esl = QVBoxLayout(self.empty_state)
		esl.setContentsMargins(18, 28, 18, 28)

		self.empty_state_label = QLabel("No missions to display.")
		self.empty_state_label.setObjectName("Muted")
		self.empty_state_label.setAlignment(Qt.AlignCenter)
		self.empty_state_label.setWordWrap(False)

		# make sure it can actually take space + not get stuck at tiny height
		self.empty_state_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

		# prevent Qt from eliding it weirdly
		self.empty_state_label.setMinimumWidth(1)

		esl.addWidget(self.empty_state_label, 1, Qt.AlignCenter)

		self.list_layout.addWidget(self.empty_state)
		self.list_layout.addStretch(1)

		self.empty_state.setVisible(False)

		outer.addWidget(surface, 1)

		self.state.labs_changed.connect(self.refresh)
		# Progress page should refresh when progress/notes change OR when running lab changes
		if hasattr(self.state, "progress_changed"):
			self.state.progress_changed.connect(self.refresh)
		self.state.running_changed.connect(lambda _lab: self.refresh())
		self.refresh()

	def refresh(self):
		labs = self.state.labs()
		progress = self.state.progress_map() if hasattr(self.state, "progress_map") else get_progress_map()

		total = len(labs)
		solved_count = _solved_count(labs, progress)
		total_xp = _total_xp(labs, progress)
		streak = _solve_streak_days(progress)
		completion = _completion_percent(total, solved_count)

		rank_name, rank_floor, next_name, next_floor = rank_for_xp(total_xp)

		self.rank_name.setText(rank_name)
		self.rank_sub.setText(f"{total_xp} XP")
		self.rank_icon.setPixmap(_emblem(rank_name.split()[0][0], 54))

		if next_name and next_floor is not None:
			need = max(0, next_floor - total_xp)
			span = max(1, next_floor - rank_floor)
			frac = max(0.0, min(1.0, (total_xp - rank_floor) / span))
			self.xp_bar.set_fraction(frac)
			self.rank_next.setText(f"Next rank: {next_name}  •  {need} XP to go")
		else:
			self.xp_bar.set_fraction(1.0)
			self.rank_next.setText("Max rank reached.")

		self.stat_solves._value_label.setText(str(solved_count))
		self.stat_streak._value_label.setText(str(streak))
		self.stat_completion._value_label.setText(f"{completion}%")
		self.stat_total._value_label.setText(str(total))

		rows = []
		running_id = self._running_lab_id()
		for lab in labs:
			lab_id = str(getattr(lab, "id", ""))
			p = progress.get(lab_id, {})

			solved = bool(p.get("solved_at"))
			lab_is_running = (running_id and lab_id == running_id)

			if self._filter_mode == "solved" and not solved:
				continue

			# Active = currently running lab (runtime), not "started_at"
			if self._filter_mode == "active":
				if not lab_is_running:
					continue

			if self._filter_mode == "unsolved":
				# unsolved = not solved and not currently running
				if solved or lab_is_running:
					continue

			solved_key = p.get("solved_at") or ""
			started_key = p.get("started_at") or ""
			rows.append((solved_key, started_key, lab, p))

		rows.sort(key=lambda t: (t[0] or "", t[1] or ""), reverse=True)

		self._clear_missions()

		if not rows:
			if self._filter_mode == "active":
				self.empty_state_label.setText("No lab is currently running.")
			else:
				self.empty_state_label.setText("No missions match this filter.")
			self.empty_state.setVisible(True)
			return

		self.empty_state.setVisible(False)

		for _solved_at, _started_at, lab, p in rows:
			lab_id = str(getattr(lab, "id", ""))
			is_running = (running_id and lab_id == running_id)
			self.list_layout.insertWidget(
				self.list_layout.count() - 1,
				self._make_mission_row(lab, p, is_running=is_running)
			)

	def _running_lab_id(self) -> str:
		# Prefer state if it exposes it, fall back to core.runtime
		try:
			if hasattr(self.state, "get_running_lab_id") and callable(getattr(self.state, "get_running_lab_id")):
				rid = self.state.get_running_lab_id()
				return str(rid) if rid else ""
			if hasattr(self.state, "running_lab_id"):
				rid = getattr(self.state, "running_lab_id")
				# running_lab_id might be a property or a method
				if callable(rid):
					rid = rid()
				return str(rid) if rid else ""
		except Exception:
			pass

		try:
			rid = get_running_lab()
			return str(rid) if rid else ""
		except Exception:
			return ""

	# ---- UI helpers ----
	def _set_filter(self, mode: str):
		self._filter_mode = mode
		self.refresh()

	def _filter_btn(self, text: str, mode: str) -> QPushButton:
		b = QPushButton(text)
		b.setObjectName("FilterPill")
		b.setCheckable(True)
		b.setCursor(Qt.PointingHandCursor)
		self._filter_group.addButton(b)
		b.clicked.connect(lambda: self._set_filter(mode))
		return b

	def _stat_card(self, label: str, value: str) -> QFrame:
		f = QFrame()
		f.setObjectName("StatCard")
		f.setAttribute(Qt.WA_StyledBackground, True)
		f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

		l = QVBoxLayout(f)
		l.setContentsMargins(14, 12, 14, 12)
		l.setSpacing(2)

		v = QLabel(value)
		v.setObjectName("StatValue")
		l.addWidget(v)

		t = QLabel(label)
		t.setObjectName("StatLabel")
		l.addWidget(t)

		f._value_label = v
		return f

	def _clear_missions(self):
		# Keep: empty_state (index 0) and the final stretch
		# Remove everything inserted between them
		while self.list_layout.count() > 2:
			it = self.list_layout.takeAt(1)  # always remove the widget after empty_state
			w = it.widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()

	def _make_mission_row(self, lab, p: Dict, is_running: bool = False) -> QFrame:
		# progress map may not have an entry for this lab yet
		p = p or {}

		diff = _norm_diff(getattr(lab, "difficulty", "") or "")
		base_xp = base_xp_for_difficulty(diff)

		solved = bool(p.get("solved_at"))

		earned = 0
		if solved:
			earned = base_xp

		status = "UNSOLVED"
		if solved:
			status = "SOLVED"
		elif is_running:
			status = "ACTIVE"

		row = QFrame()
		row.setObjectName("QuestRow")
		row.setAttribute(Qt.WA_StyledBackground, True)

		# Make the whole row clickable like a "mission" item
		row.setCursor(Qt.PointingHandCursor)
		row.setProperty("lab_id", str(getattr(lab, "id", "")))

		def _dot_variant_for_diff(d: str) -> str:
			d = (d or "").strip().lower()
			if d == "easy":
				return "green"
			if d == "medium":
				return "yellow"
			if d == "hard":
				return "red"
			if d == "master":
				return "purple"
			return "neutral"

		# Install a mouse handler without needing a custom widget class
		def _on_click(evt):
			try:
				if evt.button() == Qt.LeftButton:
					lab_id = row.property("lab_id") or ""
					if lab_id:
						self.lab_selected.emit(str(lab_id))
			except Exception:
				pass
			evt.accept()

		row.mousePressEvent = _on_click  # type: ignore[attr-defined]

		rl = QHBoxLayout(row)
		rl.setContentsMargins(14, 12, 14, 12)
		rl.setSpacing(12)

		size = 64

		avatar = QLabel()
		avatar.setObjectName("QuestAvatar")
		avatar.setFixedSize(size, size)
		avatar.setAlignment(Qt.AlignCenter)
		
		img = None
		try:
			imgp = getattr(lab, "image_path", None)
			if callable(imgp):
				pth = imgp()
				img = str(pth) if pth else None
		except Exception:
			img = None

		# Fallback to the old behavior if no image is available
		if img:
			ico = lab_badge_icon(getattr(lab, "name", "—"), diff, img, size)
		else:
			ico = lab_circle_icon(getattr(lab, "name", "—"), diff, size)
		avatar.setPixmap(ico.pixmap(size, size))

		rl.addWidget(avatar, 0, Qt.AlignTop)

		mid = QVBoxLayout()
		mid.setSpacing(4)
		rl.addLayout(mid, 1)

		name = QLabel(getattr(lab, "name", "—"))
		name.setObjectName("QuestTitle")
		mid.addWidget(name)

		meta = []
		if diff:
			meta.append(diff)
		if p.get("started_at"):
			meta.append(f"Started {_fmt_dt(p.get('started_at') or '')}")
		if p.get("solved_at"):
			meta.append(f"Solved {_fmt_dt(p.get('solved_at') or '')}")
		
		if solved:
			meta.append(f"Earned {earned} XP")
		meta_lbl = QLabel("  •  ".join(meta))
		meta_lbl.setObjectName("QuestMeta")
		mid.addWidget(meta_lbl)

		right = QVBoxLayout()
		right.setSpacing(6)
		right.setAlignment(Qt.AlignTop)
		rl.addLayout(right, 0)

		pill = QLabel(status)
		pill.setObjectName("QuestPill")
		pill.setProperty("variant", status.lower())
		pill.setAlignment(Qt.AlignCenter)
		right.addWidget(pill, 0, Qt.AlignRight)

		xp = QLabel(f"+{earned} XP" if solved else f"{base_xp} XP")
		xp.setObjectName("QuestXP")
		xp.setProperty("variant", "earned" if solved else "potential")
		right.addWidget(xp, 0, Qt.AlignRight)

		return row


def _fmt_dt(s: str) -> str:
	s = (s or "").strip()
	if not s:
		return ""
	return s[:10]


def _norm_diff(s: str) -> str:
	return (s or "").strip().upper()


class _XPBar(QFrame):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setObjectName("XPBar")
		self.setAttribute(Qt.WA_StyledBackground, True)
		self._fill = QFrame(self)
		self._fill.setObjectName("XPFill")
		self._fill.setAttribute(Qt.WA_StyledBackground, True)
		self._frac = 0.0

	def set_fraction(self, frac: float):
		self._frac = max(0.0, min(1.0, float(frac)))
		self._relayout()

	def resizeEvent(self, e):
		super().resizeEvent(e)
		self._relayout()

	def _relayout(self):
		w = self.width()
		h = self.height()
		fw = int(w * self._frac)
		self._fill.setGeometry(0, 0, fw, h)


def _emblem(text: str, size: int = 54) -> QPixmap:
	pm = QPixmap(size, size)
	pm.fill(Qt.transparent)
	p = QPainter(pm)
	p.setRenderHint(QPainter.Antialiasing, True)
	ring = QColor(245, 197, 66, 220)
	pen = QPen(ring)
	pen.setWidth(3)
	p.setPen(pen)
	p.setBrush(QColor(16, 20, 28, 220))
	p.drawEllipse(3, 3, size - 6, size - 6)
	p.setPen(Qt.NoPen)
	p.setBrush(QColor(245, 197, 66, 60))
	p.drawEllipse(10, 10, size - 20, size - 20)
	p.setPen(QColor(245, 247, 255, 235))
	f = QFont("Inter", max(10, int(size * 0.28)))
	f.setBold(True)
	p.setFont(f)
	p.drawText(pm.rect(), Qt.AlignCenter, text)
	p.end()
	return pm
