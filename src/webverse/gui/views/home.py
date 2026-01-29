# gui/views/home.py
from __future__ import annotations

import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QTextEdit, QComboBox, QSizePolicy, QProxyStyle, QStyle, QComboBox, QApplication,
    QFrame as QtQFrame, QStylePainter, QStyleOptionComboBox, QStyledItemDelegate, QStyleOptionViewItem
)
from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QPointF, QObject, QRectF, QRect
from PyQt5.QtGui import QCursor, QPalette, QColor, QPainter, QPen, QLinearGradient, QPainterPath

from webverse.gui.widgets.pill import Pill
from webverse.core.xp import base_xp_for_difficulty
from webverse.gui.widgets.row_hover_delegate import RowHoverDelegate


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
        self._name_inset = 26  # "more central" without actually centering

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

        # Lab Name: not centered, but shifted inward so it feels "more central"
        if index.column() == 0:
            opt.displayAlignment = Qt.AlignVCenter | Qt.AlignLeft
            opt.rect = opt.rect.adjusted(self._name_inset, 0, 0, 0)

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

        self.status_filter = OnyxComboBox()
        self.status_filter.setObjectName("FilterCombo")
        self.status_filter.addItems(["Status: Both", "Solved", "Unsolved"])
        self.status_filter.currentIndexChanged.connect(self._refresh_table)
        controls.addWidget(self.status_filter)

        self.diff_filter = OnyxComboBox()
        self.diff_filter.setObjectName("FilterCombo")
        self.diff_filter.addItems(["All Difficulties", "Easy", "Medium", "Hard", "Master"])
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
        tcl.setContentsMargins(12, 10, 12, 12)
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

        #QApplication.instance().installEventFilter(self)

        self.table.setProperty("_hoverRow", -1)
        self.table.setHorizontalHeaderLabels(["Lab Name", "XP", "Difficulty", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)  # XP
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Difficulty
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)           # Status
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

        # Replace the flat/boxy row look with capsule ("pill") rows.
        # Keeps your hover tracking (_hoverRow) + selection behavior.
        self.table.setItemDelegate(PillRowDelegate(self.table))

        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.setCursor(QCursor(Qt.PointingHandCursor))

        tcl.addWidget(self.table, 1)
        left.addWidget(table_card, 1)

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

        it_name = QTableWidgetItem(f"{lab.name}")
        it_name.setTextAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
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
        it_diff.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.table.setItem(row, 2, it_diff)

        solved = self.state.is_solved(lab.id)
        pill = Pill("Solved" if solved else "Unsolved", variant="success" if solved else "warn")
        pill.setFixedHeight(36)
        self.table.setRowHeight(row, 60)

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
