# gui/views/labs_browse.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QModelIndex, QSize, QRect, QPoint, QPointF, QAbstractListModel, QEvent, QObject
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPen, QBrush, QPalette, QColor

from PyQt5.QtWidgets import (
	QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
	QLineEdit, QComboBox, QListView,
	QStyledItemDelegate, QStyleOptionViewItem,
	QSizePolicy, QProxyStyle, QStyle, QApplication, QFrame as QtQFrame,
	QStylePainter, QStyleOptionComboBox
)

from webverse.core.runtime import get_running_lab
from webverse.core.xp import base_xp_for_difficulty
from webverse.gui.util_avatar import lab_circle_icon

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


@dataclass
class _LabCard:
	lab_id: str
	name: str
	slug: str
	difficulty: str
	status: str
	xp: int


class _LabsGridModel(QAbstractListModel):
	ROLE_LAB_ID = Qt.UserRole + 1
	ROLE_CARD = Qt.UserRole + 2

	def __init__(self, cards: Optional[List[_LabCard]] = None, parent=None):
		super().__init__(parent)
		self._cards: List[_LabCard] = cards or []

	def rowCount(self, parent=QModelIndex()):
		if parent.isValid():
			return 0
		return len(self._cards)

	def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
		if not index.isValid():
			return None
		card = self._cards[index.row()]
		if role == Qt.DisplayRole:
			return card.name
		if role == Qt.DecorationRole:
			return lab_circle_icon(card.name, card.difficulty, 38)
		if role == self.ROLE_LAB_ID:
			return card.lab_id
		if role == self.ROLE_CARD:
			return card
		return None

	def set_cards(self, cards: List[_LabCard]):
		self.beginResetModel()
		self._cards = cards
		self.endResetModel()


class _LabCardDelegate(QStyledItemDelegate):
	def __init__(self, parent=None):
		super().__init__(parent)

	def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
		card: _LabCard = index.data(_LabsGridModel.ROLE_CARD)
		if not card:
			super().paint(painter, option, index)
			return

		painter.save()
		painter.setRenderHint(QPainter.Antialiasing, True)

		r = option.rect.adjusted(6, 6, -6, -6)

		hover = bool(option.state & QStyle.State_MouseOver)
		pressed = bool(option.state & QStyle.State_Sunken)

		bg = QColor(10, 12, 16, 178)
		bd = QColor(255, 255, 255, 18)
		if hover:
			bg = QColor(14, 18, 26, 200)
			bd = QColor(245, 197, 66, 90)
		if pressed:
			bg = QColor(16, 22, 32, 220)
			bd = QColor(245, 197, 66, 140)

		painter.setBrush(QBrush(bg))
		painter.setPen(QPen(bd, 1))
		painter.drawRoundedRect(r, 18, 18)

		# icon
		icon = index.data(Qt.DecorationRole)
		icon_size = 40
		ix = r.left() + 14
		iy = r.top() + 14
		if icon:
			pm = icon.pixmap(icon_size, icon_size)
			painter.drawPixmap(ix, iy, pm)

		# text metrics
		fm = QFontMetrics(option.font)
		title_x = ix + icon_size + 12
		title_w = r.right() - title_x - 14

		title = card.name or "—"
		subtitle = card.slug or ""

		# title
		painter.setPen(QColor(245, 247, 255, 235))
		t_rect = QRect(title_x, iy - 1, title_w, 22)
		painter.drawText(t_rect, Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(title, Qt.ElideRight, title_w))

		# subtitle
		painter.setPen(QColor(235, 241, 255, 150))
		s_rect = QRect(title_x, iy + 20, title_w, 18)
		painter.drawText(s_rect, Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(subtitle, Qt.ElideRight, title_w))

		# bottom meta row (Difficulty / Status / XP)
		meta_y = r.bottom() - 26
		meta = f"{(card.difficulty or 'Unknown').title()}   •   {card.status}   •   {card.xp} XP"
		painter.setPen(QColor(235, 241, 255, 165))
		painter.drawText(QRect(r.left() + 14, meta_y, r.width() - 28, 18), Qt.AlignLeft | Qt.AlignVCenter, meta)

		painter.restore()

	def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
		return QSize(330, 116)


def _force_dark_combo_popup(cb: QComboBox):
	view = cb.view()

	class _PopupFix(QObject):
		def eventFilter(self, obj, ev):
			if ev.type() == QEvent.Show:
				w = view.window()  # this is the popup top-level widget (private container)
				# Force a dark palette (kills the white menu panel on many styles)
				pal = w.palette()
				pal.setColor(QPalette.Window, QColor(10, 12, 16))
				pal.setColor(QPalette.Base, QColor(10, 12, 16))
				pal.setColor(QPalette.Text, QColor(235, 241, 255))
				pal.setColor(QPalette.WindowText, QColor(235, 241, 255))
				w.setPalette(pal)
				w.setAutoFillBackground(True)

				# And force background via QSS on the popup WINDOW too
				w.setStyleSheet("""
					QWidget { background: rgba(10,12,16,0.96); color: rgba(235,241,255,0.92); }
					QAbstractItemView { background: transparent; color: rgba(235,241,255,0.92); }
				""")
			return False

	fixer = _PopupFix(cb)
	view.window().installEventFilter(fixer)
	cb._popup_fixer = fixer  # keep alive (important)

class LabsBrowseView(QWidget):
	request_open_lab = pyqtSignal(str)

	def __init__(self, state):
		super().__init__()
		self.state = state

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(12)

		surface = QFrame()
		surface.setObjectName("ContentSurface")
		outer.addWidget(surface, 1)

		content = QVBoxLayout(surface)
		content.setContentsMargins(22, 18, 22, 18)
		content.setSpacing(14)

		title = QLabel("Browse Labs")
		title.setObjectName("H1")
		content.addWidget(title)

		subtitle = QLabel("Advanced search, filtering, and sorting. Double-click a lab to open its page.")
		subtitle.setObjectName("Muted")
		content.addWidget(subtitle)

		# --- ADVANCED FILTER BAR ---
		filters = QHBoxLayout()
		filters.setSpacing(12)

		self.q = QLineEdit()
		self.q.setObjectName("SearchBox")
		self.q.setPlaceholderText("Search name, id, description…")
		self.q.textChanged.connect(self._refresh)
		filters.addWidget(self.q, 1)

		self.status = OnyxComboBox()
		self.status.setObjectName("FilterCombo")
		self.status.addItems(["Status: Any", "Status: Solved", "Status: Active", "Status: Unsolved"])
		self.status.currentIndexChanged.connect(self._refresh)

		# Style the popup deterministically via QSS
		self.status.view().setObjectName("ComboPopup")
		try:
			self.status.view().setFrameShape(QtQFrame.NoFrame)
		except Exception:
			pass

		filters.addWidget(self.status)

		self.diff = OnyxComboBox()
		self.diff.setObjectName("FilterCombo")
		self.diff.addItems(["Difficulty: Any", "Easy", "Medium", "Hard", "Master"])
		self.diff.currentIndexChanged.connect(self._refresh)

		self.diff.view().setObjectName("ComboPopup")
		try:
			self.diff.view().setFrameShape(QtQFrame.NoFrame)
		except Exception:
			pass

		filters.addWidget(self.diff)

		self.sort = OnyxComboBox()
		self.sort.setObjectName("FilterCombo")
		self.sort.addItems(["Sort: Unsolved first", "Sort: Name A→Z", "Sort: Difficulty", "Sort: XP (High→Low)"])
		self.sort.currentIndexChanged.connect(self._refresh)

		self.sort.view().setObjectName("ComboPopup")
		try:
			self.sort.view().setFrameShape(QtQFrame.NoFrame)
		except Exception:
			pass

		for cb in (self.status, self.diff, self.sort):
			_force_dark_combo_popup(cb)

		filters.addWidget(self.sort)

		content.addLayout(filters)

		# --- CARD GRID ---
		self.grid = QListView()
		self.grid.setObjectName("LabsGrid")
		self.grid.setViewMode(QListView.IconMode)
		self.grid.setResizeMode(QListView.Adjust)
		self.grid.setWrapping(True)
		self.grid.setSpacing(10)
		self.grid.setUniformItemSizes(True)
		self.grid.setMouseTracking(True)
		self.grid.setSelectionMode(QListView.NoSelection)
		self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

		self._model = _LabsGridModel([])
		self.grid.setModel(self._model)
		self.grid.setItemDelegate(_LabCardDelegate(self.grid))

		# Make cards feel snappy on hover/click
		self.grid.viewport().setAttribute(Qt.WA_Hover, True)

		self.grid.clicked.connect(self._open_lab)
		content.addWidget(self.grid, 1)

		self._refresh()

	def showEvent(self, event):
		super().showEvent(event)
		# force a relayout once geometry is real, so grid wraps nicely immediately
		QApplication.processEvents()

	def eventFilter(self, obj, event):
		return super().eventFilter(obj, event)

	def _running_lab_id(self) -> str:
		try:
			rid = get_running_lab()
			return str(rid) if rid else ""
		except Exception:
			return ""

	def _labs(self):
		return self.state.labs()

	def _progress(self):
		return self.state.progress_map() if hasattr(self.state, "progress_map") else {}

	def _refresh(self):
		labs = list(self._labs())
		prog = self._progress()
		q = (self.q.text() or "").strip().lower()
		running_id = self._running_lab_id()

		def status_of(lab_id: str) -> str:
			p = prog.get(lab_id, {})
			if p.get("solved_at"):
				return "Solved"

			if running_id and lab_id == running_id:
				return "Active"

			if p.get("started_at"):
				return "Active"
			return "Unsolved"

		# filter: query
		if q:
			out = []
			for lab in labs:
				hay = " ".join([
					(getattr(lab, "name", "") or ""),
					(getattr(lab, "id", "") or ""),
					(getattr(lab, "description", "") or ""),
				]).lower()
				if q in hay:
					out.append(lab)
			labs = out

		# filter: difficulty
		diff = self.diff.currentText().strip().lower()
		if diff != "difficulty: any":
			labs = [l for l in labs if (getattr(l, "difficulty", "") or "").strip().lower() == diff]

		# filter: status
		sidx = self.status.currentIndex()
		if sidx != 0:
			wanted = {1: "Solved", 2: "Active", 3: "Unsolved"}[sidx]
			labs = [l for l in labs if status_of(str(getattr(l, "id", ""))) == wanted]

		# sort
		rank = {"easy": 0, "medium": 1, "hard": 2, "master": 3}
		sort_mode = self.sort.currentIndex()

		def _diff_key(L):
			return rank.get((getattr(L, "difficulty", "") or "").strip().lower(), 99)

		def _xp_key(L):
			return base_xp_for_difficulty(getattr(L, "difficulty", "") or "")

		if sort_mode == 0:  # unsolved first
			labs.sort(key=lambda L: (
				status_of(str(getattr(L, "id", ""))) == "Solved",
				status_of(str(getattr(L, "id", ""))) == "Active",
				_diff_key(L),
				(getattr(L, "name", "") or "").lower(),
			))
		elif sort_mode == 1:  # name
			labs.sort(key=lambda L: (getattr(L, "name", "") or "").lower())
		elif sort_mode == 2:  # difficulty
			labs.sort(key=lambda L: (_diff_key(L), (getattr(L, "name", "") or "").lower()), reverse=True)
		else:  # XP high -> low
			labs.sort(key=lambda L: (_xp_key(L), (getattr(L, "name", "") or "").lower()), reverse=True)

		cards: List[_LabCard] = []
		for lab in labs:
			lab_id = str(getattr(lab, "id", ""))
			name = str(getattr(lab, "name", "—") or "—")
			slug = lab_id
			difficulty = str(getattr(lab, "difficulty", "") or "Unknown")
			status = status_of(lab_id)
			xp = base_xp_for_difficulty(difficulty)
			cards.append(_LabCard(lab_id=lab_id, name=name, slug=slug, difficulty=difficulty, status=status, xp=xp))

		self._model.set_cards(cards)

	def _open_lab(self, index: QModelIndex):
		lab_id = index.data(_LabsGridModel.ROLE_LAB_ID)
		if lab_id:
			self.request_open_lab.emit(str(lab_id))
