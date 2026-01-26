# gui/views/home.py
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QTextEdit, QComboBox, QSizePolicy, QProxyStyle, QStyle, QComboBox, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QPointF
from PyQt5.QtGui import QCursor, QPalette, QColor, QPainter, QPen

from gui.widgets.pill import Pill
from gui.widgets.row_hover_delegate import RowHoverDelegate

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


class HomeView(QWidget):
    nav_labs = pyqtSignal()
    request_select_lab = pyqtSignal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state

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

        self.card_total = self._stat_card("Total Labs", "0", "Discovered from /labs")
        self.card_solved = self._stat_card("Solved", "0", "Flags accepted")
        self.card_unsolved = self._stat_card("Unsolved", "0", "Available wins")
        self.card_attempts = self._stat_card("Attempts", "0", "Total flag submissions")

        stats.addWidget(self.card_total)
        stats.addWidget(self.card_solved)
        stats.addWidget(self.card_unsolved)
        stats.addWidget(self.card_attempts)
        root.addLayout(stats)

        # ---- Main row: table + notes ----
        main = QHBoxLayout()
        main.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(10)

        # Controls (search + filters)
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Labs…")
        self.search.textChanged.connect(self._refresh_table)
        controls.addWidget(self.search, 1)

        self.status_filter = QComboBox()
        self.status_filter.setObjectName("FilterCombo")
        self.status_filter.addItems(["Status: Both", "Solved", "Unsolved"])
        self.status_filter.currentIndexChanged.connect(self._refresh_table)
        controls.addWidget(self.status_filter)

        self.diff_filter = QComboBox()
        self.diff_filter.setObjectName("FilterCombo")
        self.diff_filter.addItems(["All Difficulties", "Easy", "Medium", "Hard", "Master"])
        self.diff_filter.currentIndexChanged.connect(self._refresh_table)
        controls.addWidget(self.diff_filter)

        self._combo_style = OnyxComboStyle()
        self.status_filter.setStyle(self._combo_style)
        self.diff_filter.setStyle(self._combo_style)

        left.addLayout(controls)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("LabsTable")
        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)

        #QApplication.instance().installEventFilter(self)

        self.table.setProperty("_hoverRow", -1)
        self.table.setHorizontalHeaderLabels(["Lab Name", "Difficulty", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
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

        self.table.setItemDelegate(RowHoverDelegate(self.table))
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.setCursor(QCursor(Qt.PointingHandCursor))

        left.addWidget(self.table, 1)

        main.addLayout(left, 3)

        # Notes panel
        notes = QFrame()
        notes.setObjectName("Card")
        nl = QVBoxLayout(notes)
        nl.setContentsMargins(16, 14, 16, 14)
        nl.setSpacing(10)

        title = QLabel("Notes")
        title.setObjectName("H2")
        nl.addWidget(title)

        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Write notes here…")
        nl.addWidget(self.notes, 1)

        main.addWidget(notes, 1)

        root.addLayout(main, 1)

        self._refresh_all()

    def _stat_card(self, label: str, value: str, sub: str) -> QFrame:
        card = QFrame()
        card.setObjectName("StatCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)

        v = QLabel(value)
        v.setObjectName("StatValue")
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
        total = len(labs)
        solved = sum(1 for x in labs if self.state.is_solved(x.id))
        unsolved = total - solved
        attempts = self.state.total_attempts()

        self.card_total._value_label.setText(str(total))
        self.card_solved._value_label.setText(str(solved))
        self.card_unsolved._value_label.setText(str(unsolved))
        self.card_attempts._value_label.setText(str(attempts))

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

        it_name = QTableWidgetItem(f"{lab.name}\n{lab.id}")
        it_name.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 0, it_name)

        it_diff = QTableWidgetItem((lab.difficulty or "Unknown").title())
        it_diff.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 1, it_diff)

        solved = self.state.is_solved(lab.id)
        pill = Pill("Solved" if solved else "Unsolved", variant="success" if solved else "warn")
        pill.setFixedHeight(34)
        self.table.setRowHeight(row, 64)

        wrap = QWidget()
        wrap.setObjectName("CellWrap")
        wrap.setAttribute(Qt.WA_StyledBackground, True)
        wrap.setStyleSheet("background: transparent;")
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addStretch(1)
        wl.addWidget(pill, 0, Qt.AlignCenter)
        wl.addStretch(1)

        self.table.setCellWidget(row, 2, wrap)

        self.table.setRowHeight(row, 60)
        self.table.item(row, 0).setData(Qt.UserRole, lab.id)

    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return

        lab_id = items[0].data(Qt.UserRole)
        if lab_id:
            self.request_select_lab.emit(str(lab_id))

    def _defocus_inputs(self):
        # Drop focus highlight
        self._focus_sink.setFocus(Qt.MouseFocusReason)

        # Clear text selection highlights too
        if self.search:
            self.search.deselect()

        if self.notes:
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
                self._point_in_widget(self.notes, gp) or
                self._point_in_widget(self.status_filter, gp) or
                self._point_in_widget(self.diff_filter, gp) or
                self._point_in_popup(self.status_filter, gp) or
                self._point_in_popup(self.diff_filter, gp)
            )

            if not inside_inputs:
                self._defocus_inputs()

            return False

        return super().eventFilter(obj, event)
