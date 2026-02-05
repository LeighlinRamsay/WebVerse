# gui/views/home.py
from __future__ import annotations

import math
from PyQt5.QtWidgets import (
	QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget, QTableWidgetItem,
	QHeaderView, QLineEdit, QTextEdit, QComboBox, QSizePolicy, QProxyStyle, QStyle, QComboBox, QApplication,
	QFrame as QtQFrame, QStylePainter, QStyleOptionComboBox, QStyledItemDelegate, QStyleOptionViewItem
)

from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QPointF, QObject, QRectF, QRect, QSize, QTimer
from PyQt5.QtGui import QCursor, QPalette, QColor, QPainter, QPen, QLinearGradient, QPainterPath, QFont, QFontMetrics, QIcon, QRegion, QPixmap

from webverse.gui.widgets.pill import Pill
from webverse.core.xp import base_xp_for_difficulty
from webverse.core.progress_db import get_progress_map
from webverse.core.ranks import rank_for_xp, total_xp as _total_xp, solved_count as _solved_count, completion_percent as _completion_percent
from webverse.gui.widgets.row_hover_delegate import RowHoverDelegate
from webverse.gui.util_avatar import lab_badge_icon, lab_circle_icon


class PillRowDelegate(QStyledItemDelegate):
	"""
	Paint each table row as a single sideways capsule ("pill"):
	  - First column gets left rounded end
	  - Middle columns are seamless (no rounded corners)
	  - Last column gets right rounded end
	Hover/selected get a richer glassy look.
	"""
	def __init__(self, table: QTableWidget):
		super().__init__(table)
		self._t = table
		self._name_inset = 0   # we will truly center the lab name cell

	def _first_visible_col(self) -> int:
		# If horiz scrolled, col 0 might be offscreen. Paint on first visible col.
		for c in range(self._t.columnCount()):
			x = self._t.columnViewportPosition(c)
			w = self._t.columnWidth(c)
			if (x + w) > 0:
				return c
		return 0

	def _row_rect(self, row: int) -> QRect:
		# Build a single rect spanning the full row across all columns (viewport coords).
		first = self._first_visible_col()
		last = self._t.columnCount() - 1

		idx_first = self._t.model().index(row, first)
		r = self._t.visualRect(idx_first)

		x0 = self._t.columnViewportPosition(first)
		xl = self._t.columnViewportPosition(last)
		wl = self._t.columnWidth(last)
		x1 = xl + wl

		r.setX(x0)
		r.setWidth(max(0, x1 - x0))
		return r

	def _row_selected(self, row: int) -> bool:
		sm = self._t.selectionModel()
		if not sm:
			return False
		# QItemSelectionModel doesn't expose rootIndex() in PyQt5.
		# Just ask if any index in that row is selected.
		try:
			idx = self._t.model().index(row, 0)
			return bool(idx.isValid() and sm.isSelected(idx))
		except Exception:
			return False

	def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
		row = index.row()
		col = index.column()

		hovered = (self._t.property("_hoverRow") == row)
		selected = self._row_selected(row)

		# Paint the row "pill" ONCE (on first visible column). This removes seams/patches.
		if col == self._first_visible_col():
			painter.save()
			painter.setRenderHint(QPainter.Antialiasing, True)

			r = self._row_rect(row)
			# tighter so it feels embedded (less "floating cards")
			vpad = 7
			hpad = 12
			seg = r.adjusted(hpad, vpad, -hpad, -vpad)

			segf = QRectF(seg)
			radius = max(10.0, float(segf.height() * 0.46))

			path = QPainterPath()
			path.addRoundedRect(segf, radius, radius)

			# Match your Card material: rgba(16,20,28,0.45) + subtle stroke
			# Less glossy, more "part of the surface"
			base_fill = QColor(16, 20, 28, 105)   # ~0.41
			hover_fill = QColor(16, 20, 28, 140)  # ~0.55
			sel_fill   = QColor(16, 20, 28, 160)  # ~0.63
			painter.fillPath(path, sel_fill if selected else (hover_fill if hovered else base_fill))

			# Small top sheen (keeps it premium without going grey)
			sheen = QLinearGradient(seg.left(), seg.top(), seg.left(), seg.top() + seg.height() * 0.55)
			sheen.setColorAt(0.0, QColor(255, 255, 255, 18 if not (hovered or selected) else 26))
			sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
			painter.fillPath(path, sheen)

			# Border: white stroke normally; amber accent on selection only
			if selected:
				pen = QPen(QColor(245, 197, 66, 82))
			else:
				pen = QPen(QColor(255, 255, 255, 22 if hovered else 18))
			pen.setWidth(1)
			painter.setPen(pen)
			painter.drawPath(path)

			painter.restore()

		# --- draw text normally, but WITHOUT Qt's default selection highlight ---
		opt = QStyleOptionViewItem(option)
		opt.state &= ~QStyle.State_Selected

		# Lab Name: center icon + text as one group (true "centralized")
		if index.column() == 0:
			painter.save()
			painter.setRenderHint(QPainter.Antialiasing, True)

			r = QRect(opt.rect)
			# give it a bit of breathing room so it looks premium
			r = r.adjusted(10, 0, -10, 0)

			icon = index.data(Qt.DecorationRole)
			text = str(index.data(Qt.DisplayRole) or "")

			icon_px = int(self._t.iconSize().width())
			icon_rect = QRect(0, 0, icon_px, icon_px)
			icon_rect.moveTop(r.center().y() - icon_px // 2)

			# draw icon pinned to the far-left
			if icon:
				left_pad = 10
				icon_rect.moveLeft(r.left() + left_pad)
				try:
					icon.paint(painter, icon_rect, Qt.AlignCenter, QIcon.Normal, QIcon.Off)
				except Exception:
					pass

			# draw centered text, but clip out the icon area so it never overlaps
			if text:
				if icon:
					clip = QRegion(r)
					clip = clip.subtracted(QRegion(icon_rect.adjusted(-6, -6, 6, 6)))
					painter.setClipRegion(clip)

				painter.setPen(opt.palette.text().color())
				painter.drawText(r, Qt.AlignVCenter | Qt.AlignHCenter, text)

			painter.restore()
			return

		# other columns: default painting
		super().paint(painter, opt, index)

class OnyxComboBox(QComboBox):
	def paintEvent(self, event):
		# Draw the combobox normally (frame  label) first
		p = QStylePainter(self)
		p.setRenderHint(QPainter.Antialiasing, True)

		opt = QStyleOptionComboBox()
		self.initStyleOption(opt)

		# Important: draw both the control and the label (text)
		p.drawComplexControl(QStyle.CC_ComboBox, opt)
		p.drawControl(QStyle.CE_ComboBoxLabel, opt)

		# Now draw our own chevron INSIDE the real arrow subcontrol rect
		arrow_rect = self.style().subControlRect(
			QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self
		)
		if not arrow_rect.isValid():
			return

		# Keep it safely inside the button (avoid hugging borders)
		arrow_rect = arrow_rect.adjusted(0, 0, -2, 0)

		cx = arrow_rect.center().x()
		cy = arrow_rect.center().y() + 1
		s = max(5, min(9, arrow_rect.height() // 3))

		col = QColor(235, 241, 255, 170 if self.isEnabled() else 70)
		pen = QPen(col)
		pen.setWidth(2)
		pen.setCapStyle(Qt.RoundCap)
		pen.setJoinStyle(Qt.RoundJoin)

		p.setPen(pen)
		p.setBrush(Qt.NoBrush)
		p.drawPolyline(
			QPointF(cx - s, cy - 2),
			QPointF(cx,     cy + 3),
			QPointF(cx + s, cy - 2),
		)

class OnyxComboStyle(QProxyStyle):
	"""
	Draw a clean chevron in the combo arrow area so we don't depend on native theme assets.
	"""
	def drawComplexControl(self, control, option, painter, widget=None):
		if control == QStyle.CC_ComboBox:
			# draw everything first (frame, label, etc.)
			super().drawComplexControl(control, option, painter, widget)

			# then draw our arrow on top
			painter.save()
			painter.setRenderHint(QPainter.Antialiasing, True)

			r = self.subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, widget)
			cx = r.center().x()
			cy = r.center().y()

			c = option.palette.text().color()
			c.setAlphaF(0.85 if option.state & QStyle.State_Enabled else 0.35)

			pen = QPen(c, 2)
			pen.setCapStyle(Qt.RoundCap)
			painter.setPen(pen)

			a = 5.0
			painter.drawLine(QPointF(cx - a, cy - 1.0), QPointF(cx, cy + a - 1.0))
			painter.drawLine(QPointF(cx, cy + a - 1.0), QPointF(cx + a, cy - 1.0))

			painter.restore()
			return

		super().drawComplexControl(control, option, painter, widget)


	def drawPrimitive(self, element, option, painter, widget=None):
		if element == QStyle.PE_IndicatorArrowDown:
			painter.save()
			painter.setRenderHint(QPainter.Antialiasing, True)

			c = option.palette.text().color()
			c.setAlphaF(0.85 if option.state & QStyle.State_Enabled else 0.35)

			pen = QPen(c, 2)
			pen.setCapStyle(Qt.RoundCap)
			painter.setPen(pen)

			r = option.rect
			cx = r.center().x()
			cy = r.center().y()

			a = 5.0
			painter.drawLine(QPointF(cx - a, cy - 1.0), QPointF(cx, cy + a - 1.0))
			painter.drawLine(QPointF(cx, cy + a - 1.0), QPointF(cx + a, cy - 1.0))

			painter.restore()
			return

		super().drawPrimitive(element, option, painter, widget)


def _force_dark_combo_popup(cb: QComboBox):
	view = cb.view()

	class _PopupFix(QObject):
		def eventFilter(self, obj, ev):
			if ev.type() == QEvent.Show:
				w = view.window()  # popup top-level widget (private container)

				# Force a dark palette (kills the white menu panel on many styles)
				pal = w.palette()
				pal.setColor(QPalette.Window, QColor(10, 12, 16))
				pal.setColor(QPalette.Base, QColor(10, 12, 16))
				pal.setColor(QPalette.Text, QColor(235, 241, 255))
				pal.setColor(QPalette.WindowText, QColor(235, 241, 255))
				w.setPalette(pal)
				w.setAutoFillBackground(True)

				# Force background via QSS on the popup WINDOW too
				w.setStyleSheet("""
					QWidget { background: rgba(10,12,16,0.96); color: rgba(235,241,255,0.92); }
					QAbstractItemView { background: transparent; color: rgba(235,241,255,0.92); }
				""")
			return False

	fixer = _PopupFix(cb)
	view.window().installEventFilter(fixer)
	cb._popup_fixer = fixer  # keep alive


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
		try:
			self._frac = max(0.0, min(1.0, float(frac)))
		except Exception:
			self._frac = 0.0
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

class HomeView(QWidget):
	nav_labs = pyqtSignal()
	request_select_lab = pyqtSignal(str)

	def __init__(self, state):
		super().__init__()
		self.state = state
		self.notes = None  # notes panel may be removed; prevent attribute errors

		# Home wants a slightly larger, "HTB-like" scale.
		self._icon_px = 80
		self._row_h = 102
		self._pill_h = 44
		self._control_h = 46

		self.setFocusPolicy(Qt.StrongFocus)  # HomeView can hold focus

		self._focus_sink = QWidget(self)
		self._focus_sink.setFixedSize(1, 1)
		self._focus_sink.setFocusPolicy(Qt.StrongFocus)
		self._focus_sink.hide()

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(12)

		surface = QFrame()
		surface.setObjectName("ContentSurface")
		outer.addWidget(surface, 1)

		root = QVBoxLayout(surface)
		root.setContentsMargins(22, 18, 22, 18)
		root.setSpacing(14)

		# ---- Stats row ----
		stats = QHBoxLayout()
		stats.setSpacing(12)

		# Rank card (takes space of two boxes)
		self.rank_card = QFrame()
		self.rank_card.setObjectName("PlayerCard")
		self.rank_card.setAttribute(Qt.WA_StyledBackground, True)
		self.rank_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

		rcl = QHBoxLayout(self.rank_card)
		rcl.setContentsMargins(14, 14, 14, 14)
		rcl.setSpacing(12)

		self.rank_icon = QLabel()
		self.rank_icon.setFixedSize(54, 54)
		rcl.addWidget(self.rank_icon, 0, Qt.AlignTop)

		col = QVBoxLayout()
		col.setSpacing(6)
		rcl.addLayout(col, 1)

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

		self.card_total = self._stat_card("Total Labs", "0", "Discovered from /labs")
		self.card_completion = self._stat_card("Completion", "0%", "Solved / Total")

		stats.addWidget(self.rank_card, 2)
		stats.addWidget(self.card_total, 1)
		stats.addWidget(self.card_completion, 1)
		root.addLayout(stats)

		# Give the stat cards more presence.
		for c in (self.rank_card, self.card_total, self.card_completion):
			c.setMinimumHeight(94)

		# ---- Main row: table ----
		main = QHBoxLayout()
		main.setSpacing(14)

		left = QVBoxLayout()
		left.setSpacing(10)

		# Controls (search + filters)
		controls = QHBoxLayout()
		controls.setSpacing(10)

		self.search = QLineEdit()
		self.search.setPlaceholderText("Search Labs…")
		self.search.setFixedHeight(self._control_h)
		self.search.textChanged.connect(self._refresh_table)
		controls.addWidget(self.search, 1)

		self.status_filter = OnyxComboBox()
		self.status_filter.setObjectName("FilterCombo")
		self.status_filter.addItems(["Status: Both", "Solved", "Unsolved"])
		self.status_filter.setFixedHeight(self._control_h)
		self.status_filter.currentIndexChanged.connect(self._refresh_table)
		controls.addWidget(self.status_filter)

		self.diff_filter = OnyxComboBox()
		self.diff_filter.setObjectName("FilterCombo")
		self.diff_filter.addItems(["All Difficulties", "Easy", "Medium", "Hard", "Master"])
		self.diff_filter.setFixedHeight(self._control_h)
		self.diff_filter.currentIndexChanged.connect(self._refresh_table)
		controls.addWidget(self.diff_filter)

		# Make popup deterministic + dark (kills white background)
		for cb in (self.status_filter, self.diff_filter):
			cb.view().setObjectName("ComboPopup")
			try:
				cb.view().setFrameShape(QtQFrame.NoFrame)
			except Exception:
				pass
			_force_dark_combo_popup(cb)

		left.addLayout(controls)

		# Wrap the table in a Card so the list feels "placed" (not floating in the surface)
		table_card = QFrame()
		table_card.setObjectName("Card")
		tcl = QVBoxLayout(table_card)
		tcl.setContentsMargins(14, 12, 14, 14)
		tcl.setSpacing(8)

		# Optional small header label (makes the list feel intentional)
		list_title = QLabel("Labs")
		list_title.setObjectName("H2")
		tcl.addWidget(list_title)

		self.table = QTableWidget(0, 4)
		self.table.setObjectName("LabsTable")
		self.table.setMouseTracking(True)
		self.table.viewport().setMouseTracking(True)
		self.table.viewport().installEventFilter(self)

		self.table.setIconSize(QSize(self._icon_px, self._icon_px))

		# Slightly larger table typography.
		f = QFont(self.table.font())
		try:
			# Prefer pixel sizing (consistent across DPI themes)
			f.setPixelSize(max(14, f.pixelSize() + 2 if f.pixelSize() > 0 else 15))
		except Exception:
			pass
		self.table.setFont(f)

		self.table.setProperty("_hoverRow", -1)
		self.table.setHorizontalHeaderLabels(["Lab Name", "XP", "Difficulty", "Status"])
		self.table.horizontalHeader().setStretchLastSection(True)
		self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
		self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # XP
		self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Difficulty
		self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)           # Status
		self.table.verticalHeader().setVisible(False)

		# Make rows tall enough for bigger lab icons (HTB-like)
		try:
			self.table.verticalHeader().setDefaultSectionSize(self._row_h)
		except Exception:
			pass

		self.table.setShowGrid(False)
		self.table.setSelectionBehavior(QTableWidget.SelectRows)
		self.table.setSelectionMode(QTableWidget.SingleSelection)
		self.table.setAlternatingRowColors(False)

		# prevent native selection highlight (Windows blue) from bleeding through
		pal = self.table.palette()
		pal.setColor(QPalette.Highlight, QColor(0, 0, 0, 0))
		pal.setColor(QPalette.HighlightedText, pal.color(QPalette.Text))
		self.table.setPalette(pal)
		self.table.setFocusPolicy(Qt.NoFocus)

		# Replace the flat/boxy row look with capsule ("pill") rows.
		# Keeps your hover tracking (_hoverRow) + selection behavior.
		self.table.setItemDelegate(PillRowDelegate(self.table))

		self.table.cellClicked.connect(self._on_row_clicked)
		self.table.itemSelectionChanged.connect(self._on_select)
		self.table.setCursor(QCursor(Qt.PointingHandCursor))

		tcl.addWidget(self.table, 1)
		left.addWidget(table_card, 1)

		main.addLayout(left, 1)

		root.addLayout(main, 1)

		self._refresh_all()

		# Keep Home stats live
		try:
			self.state.labs_changed.connect(self._refresh_all)
		except Exception:
			pass
		try:
			if hasattr(self.state, "progress_changed"):
				self.state.progress_changed.connect(self._refresh_all)
		except Exception:
			pass
		try:
			self.state.running_changed.connect(lambda _lab: self._refresh_all())
		except Exception:
			pass

	def _stat_card(self, label: str, value: str, sub: str) -> QFrame:
		card = QFrame()
		card.setObjectName("StatCard")
		lay = QVBoxLayout(card)
		lay.setContentsMargins(18, 16, 18, 16)
		lay.setSpacing(4)

		v = QLabel(value)
		v.setObjectName("StatValue")
		fv = QFont(v.font())
		try:
			fv.setPixelSize(28)
		except Exception:
			pass
		v.setFont(fv)

		lay.addWidget(v)

		l = QLabel(label)
		l.setObjectName("StatLabel")
		lay.addWidget(l)

		s = QLabel(sub)
		s.setObjectName("Muted")
		lay.addWidget(s)

		card._value_label = v
		return card

	def _refresh_all(self):
		self._refresh_stats()
		self._refresh_table()

	def _refresh_stats(self):
		labs = self.state.labs()
		progress = self.state.progress_map() if hasattr(self.state, "progress_map") else get_progress_map()

		total = len(labs)
		solved = _solved_count(labs, progress)
		completion = _completion_percent(total, solved)

		total_xp = _total_xp(labs, progress)
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

		self.card_total._value_label.setText(str(total))
		self.card_completion._value_label.setText(f"{completion}%")

	def _filtered_labs(self):
		q = (self.search.text() or "").strip().lower()
		status = self.status_filter.currentText()
		diff = self.diff_filter.currentText()

		out = []
		for lab in self.state.labs():
			if q:
				hay = f"{lab.name} {lab.id} {lab.description}".lower()
				if q not in hay:
					continue

			solved = self.state.is_solved(lab.id)
			if status == "Solved" and not solved:
				continue
			if status == "Unsolved" and solved:
				continue

			if diff != "All Difficulties":
				if (lab.difficulty or "").lower() != diff.lower():
					continue

			out.append(lab)
		return out

	def _refresh_table(self):
		labs = self._filtered_labs()
		self.table.setRowCount(0)
		for lab in labs:
			self._add_row(lab)

	def _add_row(self, lab):
		row = self.table.rowCount()
		self.table.insertRow(row)

		# Bigger typography for Lab Name + Difficulty (keep XP/Status as-is)
		name_font = QFont(self.table.font())
		diff_font = QFont(self.table.font())
		try:
			base_px = name_font.pixelSize()
			if base_px <= 0:
				base_px = 15
			name_font.setPixelSize(base_px + 3)
			diff_font.setPixelSize(base_px + 2)
		except Exception:
			# fallback to point sizing
			name_font.setPointSize(max(12, name_font.pointSize() + 2))
			diff_font.setPointSize(max(11, diff_font.pointSize() + 1))

		it_name = QTableWidgetItem(f"{lab.name}")
		try:
			size = self._icon_px
			img = None
			imgp = getattr(lab, "image_path", None)
			if callable(imgp):
				p = imgp()
				img = str(p) if p else None
			if img:
				ico = lab_badge_icon(lab.name, getattr(lab, "difficulty", None), img, size)
			else:
				ico = lab_circle_icon(lab.name, getattr(lab, "difficulty", None), size)
			it_name.setIcon(ico)
		except Exception:
			pass
		it_name.setTextAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
		it_name.setFont(name_font)
		it_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
		self.table.setItem(row, 0, it_name)

		# Match Progress page XP (base_xp_for_difficulty)
		base_xp = base_xp_for_difficulty(getattr(lab, "difficulty", "") or "")
		it_xp = QTableWidgetItem(f"{int(base_xp)}")
		it_xp.setTextAlignment(Qt.AlignCenter)
		it_xp.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
		self.table.setItem(row, 1, it_xp)

		it_diff = QTableWidgetItem((lab.difficulty or "Unknown").title())
		it_diff.setTextAlignment(Qt.AlignCenter)
		it_diff.setFont(diff_font)
		it_diff.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
		self.table.setItem(row, 2, it_diff)

		solved = self.state.is_solved(lab.id)
		pill = Pill("Solved" if solved else "Unsolved", variant="success" if solved else "warn")
		pill.setFixedHeight(self._pill_h)
		self.table.setRowHeight(row, self._row_h)

		wrap = QWidget()
		wrap.setObjectName("CellWrap")
		wrap.setAttribute(Qt.WA_StyledBackground, True)
		wrap.setAttribute(Qt.WA_TranslucentBackground, True)
		wrap.setStyleSheet("background: transparent;")
		wl = QHBoxLayout(wrap)
		wl.setContentsMargins(0, 0, 0, 0)
		wl.addStretch(1)
		wl.addWidget(pill, 0, Qt.AlignCenter)
		wl.addStretch(1)

		self.table.setCellWidget(row, 3, wrap)
		it_name.setData(Qt.UserRole, lab.id)

	def _on_row_clicked(self, row: int, col: int):
		it = self.table.item(row, 0)
		if not it:
			return
		lab_id = it.data(Qt.UserRole)
		if lab_id:
			self.request_select_lab.emit(str(lab_id))
			self._clear_table_selection_soon()

	def _clear_table_selection_soon(self):
		# Defer until after Qt finishes processing the click/selection event.
		def _do():
			try:
				self.table.blockSignals(True)
				self.table.clearSelection()
				self.table.setCurrentItem(None)
			except Exception:
				pass
			finally:
				try:
					self.table.blockSignals(False)
				except Exception:
					pass
		QTimer.singleShot(0, _do)

	def _on_select(self):
		row = self.table.currentRow()
		if row < 0:
			return

		it = self.table.item(row, 0)
		if not it:
			return
		lab_id = it.data(Qt.UserRole)
		if lab_id:
			self.request_select_lab.emit(str(lab_id))
			# Ensure when you return to Home, nothing is left "selected".
			self._clear_table_selection_soon()

	def _defocus_inputs(self):
		# Drop focus highlight
		self._focus_sink.setFocus(Qt.MouseFocusReason)

		# Clear text selection highlights too
		if self.search:
			self.search.deselect()

		if getattr(self, "notes", None):
			c = self.notes.textCursor()
			c.clearSelection()
			self.notes.setTextCursor(c)

		# Close any open combo popup
		for cb in (self.status_filter, self.diff_filter):
			if cb and cb.view() and cb.view().isVisible():
				cb.hidePopup()

	def _point_in_widget(self, w, global_pos) -> bool:
		if not w or not w.isVisible():
			return False
		local = w.mapFromGlobal(global_pos)
		return w.rect().contains(local)

	def _point_in_popup(self, cb, global_pos) -> bool:
		if not cb:
			return False
		v = cb.view()
		if not v or not v.isVisible():
			return False
		local = v.mapFromGlobal(global_pos)
		return v.rect().contains(local)

	def eventFilter(self, obj, event):
		if obj is self.table.viewport():
			if event.type() == QEvent.MouseMove:
				row = self.table.rowAt(event.pos().y())
				cur = self.table.property("_hoverRow")
				if row != cur:
					self.table.setProperty("_hoverRow", row)
					self.table.viewport().update()
				return False

			if event.type() == QEvent.Leave:
				if self.table.property("_hoverRow") != -1:
					self.table.setProperty("_hoverRow", -1)
					self.table.viewport().update()
				return False

		if event.type() == QEvent.MouseButtonPress:
			gp = event.globalPos()

			inside_inputs = (
				self._point_in_widget(self.search, gp) or
				self._point_in_widget(getattr(self, "notes", None), gp) or
				self._point_in_widget(self.status_filter, gp) or
				self._point_in_widget(self.diff_filter, gp) or
				self._point_in_popup(self.status_filter, gp) or
				self._point_in_popup(self.diff_filter, gp)
			)

			if not inside_inputs:
				self._defocus_inputs()

			return False

		return super().eventFilter(obj, event)
