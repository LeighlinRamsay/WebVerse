# gui/views/labs_browse.py
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QTimer
from PyQt5.QtGui import QCursor

from gui.util_avatar import lab_circle_icon
from gui.widgets.row_hover_delegate import RowHoverDelegate


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

        self.status = QComboBox()
        self.status.setObjectName("FilterBox")
        self.status.addItems(["Status: Any", "Status: Solved", "Status: Active", "Status: Unsolved"])
        self.status.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.status)

        self.diff = QComboBox()
        self.diff.setObjectName("FilterBox")
        self.diff.addItems(["Difficulty: Any", "Easy", "Medium", "Hard", "Master"])
        self.diff.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.diff)

        self.sort = QComboBox()
        self.sort.setObjectName("FilterBox")
        self.sort.addItems(["Sort: Unsolved first", "Sort: Name A→Z", "Sort: Difficulty", "Sort: Attempts"])
        self.sort.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.sort)

        content.addLayout(filters)

        # --- RESULTS TABLE ---
        self.table = QTableWidget()
        self.table.setObjectName("LabsTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Lab", "Difficulty", "Status", "Attempts"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        # Single click should not "select" (it changes icon tint on some styles).
        # Double click opens; hover handles visuals.
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)

        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)

        self.table.viewport().setAttribute(Qt.WA_Hover, True)

        # Row-hover plumbing (same as HomeView)
        self.table.viewport().installEventFilter(self)
        self.table.setProperty("_hoverRow", -1)
        self.table.setItemDelegate(RowHoverDelegate(self.table))

        # Fix the classic "row 0 doesn't hover until something else happens"
        QTimer.singleShot(0, self._sync_hover_to_cursor)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.table.cellDoubleClicked.connect(self._open_lab)
        content.addWidget(self.table, 1)

        self._refresh()

    def showEvent(self, event):
        super().showEvent(event)
        # Cursor may already be over row 0 before the table has real geometry.
        # Do an immediate sync + a short delayed sync after layout/paint settles.
        QTimer.singleShot(0, self._sync_hover_to_cursor)
        QTimer.singleShot(40, self._sync_hover_to_cursor)

    def _sync_hover_to_cursor(self):
        if not self.table or not self.table.viewport():
            return
        pos = self.table.viewport().mapFromGlobal(QCursor.pos())
        self._set_hover_from_pos(pos)

    def _set_hover_from_pos(self, pos):
        # indexAt() can return an invalid index for the first row depending on style/padding.
        # rowAt() is stable because it only uses y-coord -> perfect for row-hover effects.
        
        y = int(pos.y())
        row = self.table.rowAt(y)

        # IMPORTANT FIX:
        # With our rounded/padded table styling, there's often a tiny "dead strip" at the very
        # top of the viewport where rowAt() returns -1 even though the cursor is visually over row 0.
        # So if rowAt() fails, but the cursor is still within the vertical band of row 0, force row 0.
        if row < 0 and self.table.rowCount() > 0:
            top0 = self.table.rowViewportPosition(0)
            h0 = self.table.rowHeight(0)
            if 0 <= y < (top0 + h0):
                row = 0

        # If we're not over any row (e.g., empty space below rows), clear hover.
        if row < 0:
            row = -1

        cur = int(self.table.property("_hoverRow") or -1)
        if row != cur:
            self.table.setProperty("_hoverRow", row)
            self.table.viewport().update()

    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            t = event.type()
            if t in (QEvent.MouseMove, QEvent.HoverMove):
                self._set_hover_from_pos(event.pos())
            elif t in (QEvent.HoverEnter, QEvent.Enter):
                # Enter has no .pos() in PyQt5 -> sync from cursor
                pos = self.table.viewport().mapFromGlobal(QCursor.pos())
                self._set_hover_from_pos(pos)

            elif t in (QEvent.Show, QEvent.Resize):
                # Geometry changes can affect indexAt() for row 0
                QTimer.singleShot(0, self._sync_hover_to_cursor)

            elif t in (QEvent.Leave, QEvent.HoverLeave):
                cur = int(self.table.property("_hoverRow") or -1)
                if cur != -1:
                    self.table.setProperty("_hoverRow", -1)
                    self.table.viewport().update()
        return super().eventFilter(obj, event)

    def _labs(self):
        return self.state.labs()

    def _progress(self):
        return self.state.progress_map() if hasattr(self.state, "progress_map") else {}

    def _refresh(self):
        labs = list(self._labs())
        prog = self._progress()
        q = (self.q.text() or "").strip().lower()

        def status_of(lab_id: str):
            p = prog.get(lab_id, {})
            if p.get("solved_at"):
                return "Solved"
            if p.get("started_at"):
                return "Active"
            return "Unsolved"

        # filter: query
        if q:
            out = []
            for lab in labs:
                hay = " ".join([
                    (lab.name or ""),
                    (lab.id or ""),
                    (lab.description or ""),
                ]).lower()
                if q in hay:
                    out.append(lab)
            labs = out

        # filter: difficulty
        diff = self.diff.currentText().strip().lower()
        if diff != "difficulty: any":
            labs = [l for l in labs if (l.difficulty or "").strip().lower() == diff]

        # filter: status
        sidx = self.status.currentIndex()
        if sidx != 0:
            wanted = {1: "Solved", 2: "Active", 3: "Unsolved"}[sidx]
            labs = [l for l in labs if status_of(l.id) == wanted]

        # sort
        rank = {"easy": 0, "medium": 1, "hard": 2, "master": 3}
        sort_mode = self.sort.currentIndex()
        if sort_mode == 0:  # unsolved first
            labs.sort(key=lambda L: (status_of(L.id) == "Solved", status_of(L.id) == "Active",
                                    rank.get((L.difficulty or "").lower(), 99), (L.name or "").lower()))
        elif sort_mode == 1:  # name
            labs.sort(key=lambda L: (L.name or "").lower())
        elif sort_mode == 2:  # difficulty
            labs.sort(key=lambda L: (rank.get((L.difficulty or "").lower(), 99), (L.name or "").lower()))
        else:  # attempts
            labs.sort(key=lambda L: int(prog.get(L.id, {}).get("attempts") or 0), reverse=True)

        self.table.setRowCount(len(labs))
        for r, lab in enumerate(labs):
            lab_item = QTableWidgetItem(f"{lab.name}\n{lab.id}")
            lab_item.setIcon(lab_circle_icon(lab.name, lab.difficulty, 38))
            lab_item.setData(Qt.UserRole, lab.id)
            self.table.setItem(r, 0, lab_item)

            d = QTableWidgetItem((lab.difficulty or "Unknown").title())
            d.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, d)

            st = QTableWidgetItem(status_of(lab.id))
            st.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 2, st)

            attempts = int(prog.get(lab.id, {}).get("attempts") or 0)
            a = QTableWidgetItem(str(attempts))
            a.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, a)

            self.table.setRowHeight(r, 62)

        # After repopulating, resync hover immediately (prevents row 0 hover weirdness)
        QTimer.singleShot(0, self._sync_hover_to_cursor)

    def _open_lab(self, row: int, col: int):
        item = self.table.item(row, 0)
        if not item:
            return
        lab_id = item.data(Qt.UserRole)
        if lab_id:
            self.request_open_lab.emit(lab_id)
