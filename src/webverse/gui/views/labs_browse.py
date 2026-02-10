# gui/views/labs_browse.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QModelIndex, QSize, QRect, QPoint, QPointF, QAbstractListModel, QEvent, QObject, QThread
from PyQt5.QtGui import QColor, QFontMetrics, QPainter, QPen, QBrush, QPalette, QColor, QFont

from PyQt5.QtWidgets import (
	QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
	QLineEdit, QComboBox, QListView,
	QStyledItemDelegate, QStyleOptionViewItem,
	QSizePolicy, QProxyStyle, QStyle, QApplication, QFrame as QtQFrame,
	QStylePainter, QStyleOptionComboBox, QPushButton
)

from webverse.core.runtime import get_running_lab
from webverse.core.xp import base_xp_for_difficulty
from webverse.gui.util_avatar import lab_badge_icon, lab_circle_icon

from webverse.gui.dialogs import InstallLabsDialog, InstallableLab
from webverse.gui.workers.remote_labs_worker import RemoteLabsWorker

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
	image_path: Optional[str] = None


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
			size = 96
			if card.image_path:
				return lab_badge_icon(card.name, card.difficulty, card.image_path, size)
			return lab_circle_icon(card.name, card.difficulty, size)
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

		# Larger inner padding to match bigger tiles
		r = option.rect.adjusted(10, 10, -10, -10)

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
		painter.drawRoundedRect(r, 22, 22)

		# icon
		icon = index.data(Qt.DecorationRole)
		icon_size = 64
		ix = r.left() + 18
		iy = r.top() + 18
		if icon:
			pm = icon.pixmap(icon_size, icon_size)
			painter.drawPixmap(ix, iy, pm)

		# Typography (bigger title + readable meta)
		title_font = QFont(option.font)
		sub_font = QFont(option.font)
		meta_font = QFont(option.font)
		try:
			base_px = title_font.pixelSize()
			if base_px <= 0:
				base_px = 15
			title_font.setPixelSize(base_px + 6)  # BIGGER name
			title_font.setBold(True)
			sub_font.setPixelSize(base_px + 2)
			meta_font.setPixelSize(base_px + 2)
		except Exception:
			title_font.setPointSize(max(14, title_font.pointSize() + 4))
			title_font.setBold(True)
			sub_font.setPointSize(max(12, sub_font.pointSize() + 2))
			meta_font.setPointSize(max(12, meta_font.pointSize() + 2))

		title_x = ix + icon_size + 16
		title_w = r.right() - title_x - 18

		title = card.name or "—"
		subtitle = card.slug or ""

		# title
		painter.setPen(QColor(245, 247, 255, 235))
		painter.setFont(title_font)
		fm_title = QFontMetrics(title_font)
		t_rect = QRect(title_x, iy - 2, title_w, 34)
		painter.drawText(t_rect, Qt.AlignLeft | Qt.AlignVCenter, fm_title.elidedText(title, Qt.ElideRight, title_w))

		# subtitle
		painter.setPen(QColor(235, 241, 255, 150))
		painter.setFont(sub_font)
		fm_sub = QFontMetrics(sub_font)
		s_rect = QRect(title_x, iy + 30, title_w, 24)
		painter.drawText(s_rect, Qt.AlignLeft | Qt.AlignVCenter, fm_sub.elidedText(subtitle, Qt.ElideRight, title_w))

		# bottom meta row (Difficulty / Status / XP)
		painter.setFont(meta_font)
		meta_y = r.bottom() - 34
		meta = f"{(card.difficulty or 'Unknown').title()}   •   {card.status}   •   {card.xp} XP"
		painter.setPen(QColor(235, 241, 255, 165))
		painter.drawText(QRect(r.left() + 18, meta_y, r.width() - 36, 24), Qt.AlignLeft | Qt.AlignVCenter, meta)

		painter.restore()

	def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
		return QSize(400, 190)


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

		# --- Remote labs ---
		self.check_new_btn = QPushButton("Check new labs")
		self.check_new_btn.setObjectName("GhostButton")
		self.check_new_btn.clicked.connect(self._check_remote_labs)
		filters.addWidget(self.check_new_btn)

		content.addLayout(filters)

		# --- CARD GRID ---
		self.grid = QListView()
		self.grid.setObjectName("LabsGrid")
		self.grid.setViewMode(QListView.IconMode)
		self.grid.setResizeMode(QListView.Adjust)
		self.grid.setWrapping(True)
		self.grid.setSpacing(16)
		self.grid.setUniformItemSizes(True)
		self.grid.setMouseTracking(True)
		self.grid.setSelectionMode(QListView.NoSelection)
		self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

		# Ensure the layout engine has enough room per item (matches delegate sizeHint)
		self.grid.setGridSize(QSize(420, 210))
		self.grid.setIconSize(QSize(96, 96))

		self._model = _LabsGridModel([])
		self.grid.setModel(self._model)
		self.grid.setItemDelegate(_LabCardDelegate(self.grid))

		# Make cards feel snappy on hover/click
		self.grid.viewport().setAttribute(Qt.WA_Hover, True)

		self.grid.clicked.connect(self._open_lab)
		content.addWidget(self.grid, 1)

		self._refresh()

		# --- Live refresh when labs are added/removed/changed ---
		# After remote install: AppState.refresh_labs() emits labs_changed,
		# but this view must listen and rebuild its model.
		try:
			if hasattr(self.state, "labs_changed"):
				self.state.labs_changed.connect(self._refresh)
		except Exception:
			pass

		# Status badges/sorting depend on progress + running lab state too.
		try:
			if hasattr(self.state, "progress_changed"):
				self.state.progress_changed.connect(self._refresh)
		except Exception:
			pass

		try:
			if hasattr(self.state, "running_changed"):
				self.state.running_changed.connect(lambda _lab=None: self._refresh())
		except Exception:
			pass

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
			img = None
			try:
				imgp = getattr(lab, "image_path", None)
				if callable(imgp):
					p = imgp()
					img = str(p) if p else None
			except Exception:
				img = None
			cards.append(_LabCard(lab_id=lab_id, name=name, slug=slug, difficulty=difficulty, status=status, xp=xp, image_path=img))

		self._model.set_cards(cards)

	def _open_lab(self, index: QModelIndex):
		lab_id = index.data(_LabsGridModel.ROLE_LAB_ID)
		if lab_id:
			self.request_open_lab.emit(str(lab_id))

	# ---- Remote labs (downloadable from OSS API) ----
	def _toast(self, level: str, msg: str, ms: int = 2200):
		w = self.window()
		fn = getattr(w, f"toast_{level}", None)
		if callable(fn):
			fn(msg, ms=ms)
			return
		# fallback: do nothing

	def _set_remote_busy(self, busy: bool):
		try:
			self.check_new_btn.setDisabled(busy)
			self.check_new_btn.setText("Checking…" if busy else "Check new labs")
		except Exception:
			pass

	def _check_remote_labs(self):
		# start worker thread
		self._set_remote_busy(True)
		self._toast("info", "Checking for new labs…", ms=1400)

		self._labs_thread = QThread()
		self._labs_worker = RemoteLabsWorker()
		self._labs_worker.moveToThread(self._labs_thread)
		self._labs_thread.started.connect(self._labs_worker.check)
		self._labs_worker.checked.connect(self._on_remote_checked)
		self._labs_worker.error.connect(self._on_remote_error)
		self._labs_worker.checked.connect(lambda _: self._labs_thread.quit())
		self._labs_worker.error.connect(lambda _: self._labs_thread.quit())
		self._labs_thread.finished.connect(self._labs_thread.deleteLater)
		self._labs_thread.start()

	def _on_remote_checked(self, labs):
		self._set_remote_busy(False)
		missing = list(labs or [])
		if not missing:
			self._toast("success", "You're up to date — no new labs.", ms=1800)
			return

		items = [InstallableLab(id=x.id, name=x.name or x.id, difficulty=x.difficulty or "unknown", version=x.version or "1", size_bytes=x.size_bytes or 0) for x in missing]
		dlg = InstallLabsDialog(items, parent=self)
		if dlg.exec_() != dlg.Accepted:
			self._toast("info", "No labs installed.", ms=1600)
			return

		selected = set(dlg.selected_ids())
		to_install = [x for x in missing if x.id in selected]
		if not to_install:
			self._toast("info", "No labs selected.", ms=1600)
			return

		self._install_remote_labs(to_install)

	def _install_remote_labs(self, labs):
		self._set_remote_busy(True)
		self._toast("info", f"Installing {len(labs)} lab(s)…", ms=1600)

		self._install_thread = QThread()
		self._install_worker = RemoteLabsWorker()
		self._install_worker.moveToThread(self._install_thread)
		self._install_thread.started.connect(lambda: self._install_worker.install(labs))
		self._install_worker.installed.connect(self._on_remote_installed)
		self._install_worker.error.connect(self._on_remote_error)
		self._install_worker.installed.connect(lambda _: self._install_thread.quit())
		self._install_worker.error.connect(lambda _: self._install_thread.quit())
		self._install_thread.finished.connect(self._install_thread.deleteLater)
		self._install_thread.start()

	def _on_remote_installed(self, ids):
		self._set_remote_busy(False)
		got = list(ids or [])
		if got:
			try:
				self.state.refresh_labs()
			except Exception:
				pass
			self._toast("success", f"Installed {len(got)} new lab(s).", ms=2200)
		else:
			self._toast("info", "Nothing installed.", ms=1800)

	def _on_remote_error(self, err: str):
		self._set_remote_busy(False)
		msg = (err or "").strip() or "Something went wrong."
		self._toast("error", msg, ms=2800)
