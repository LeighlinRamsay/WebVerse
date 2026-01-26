from __future__ import annotations

from PyQt5.QtCore import Qt, QRect, QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QBrush
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QAbstractItemView, QStyle


class RowHoverDelegate(QStyledItemDelegate):
    """
    Paint a single smooth "row hover" tile like HTB.
    No per-cell hover visuals; we paint the row background once (on column 0),
    and keep item backgrounds transparent in QSS.
    """
    def __init__(self, view: QAbstractItemView):
        super().__init__(view)
        self.view = view

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        opt = QStyleOptionViewItem(option)

        # Kill Qt's default hover/selection visuals (we control all row visuals here)
        opt.state &= ~QStyle.State_MouseOver
        opt.state &= ~QStyle.State_HasFocus
        is_selected = bool(opt.state & QStyle.State_Selected)
        opt.state &= ~QStyle.State_Selected
        opt.backgroundBrush = QBrush(Qt.NoBrush)

        hover_row = int(self.view.property("_hoverRow") or -1)
        is_hover = (index.row() == hover_row)

        # Paint the row hover background ONCE across the full row width (only from col 0)
       	# Draw the same "row tile" behind EVERY cell (clipped), so it never disappears
        # on a single column due to partial repaints.
        if is_hover or is_selected:
            model = index.model()
            last_col = max(0, model.columnCount(index.parent()) - 1)

            first = self.view.visualRect(model.index(index.row(), 0, index.parent()))
            last = self.view.visualRect(model.index(index.row(), last_col, index.parent()))

            # Build a full-row rect using THIS cell's top/height (stable) + first/last x extents.
            # (Fixes cases where row 0 doesn't hover until selection/move)
            full = QRect(
                first.left(),
                opt.rect.top(),
                max(1, last.right() - first.left() + 1),
                opt.rect.height()
            )

            # Inset so it feels like a single tile (not glued to edges)
            full.adjust(6, 6, -6, -6)

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setClipRect(opt.rect)  # only draw what's needed for this cell paint

            # IMPORTANT:
        	# Qt repaints individual cells over time (scroll, timers, focus changes, etc).
        	# If we only paint the "row tile" from column 0, other cells can repaint and
        	# lose the background. So we paint the row tile for EVERY cell, clipped to
        	# that cell's rect. This guarantees the hover stays perfect everywhere.
            if is_selected and is_hover:
                bg = QColor(245, 197, 66, 34)
                br = QColor(245, 197, 66, 92)
            elif is_selected:
                bg = QColor(245, 197, 66, 26)
                br = QColor(245, 197, 66, 78)
            else:
                bg = QColor(245, 197, 66, 20)
                br = QColor(245, 197, 66, 60)

            path = QPainterPath()
            path.addRoundedRect(QRectF(full), 14.0, 14.0)
            painter.fillPath(path, bg)
            painter.setPen(br)
            painter.drawPath(path)

            painter.restore()

        super().paint(painter, opt, index)
