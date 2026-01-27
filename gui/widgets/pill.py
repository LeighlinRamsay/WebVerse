# gui/widgets/pill.py
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel
from PyQt5.QtGui import QColor, QPainter, QPen


class Pill(QFrame):
    """
    Small status pill used inside tables/cards.
    Variants: success | warn | bad | muted
    """

    def __init__(self, text: str, variant: str = "muted", parent=None):
        super().__init__(parent)
        self.setObjectName("Pill")
        # We paint it ourselves. Kill any chance of QSS/frame painting a square box.
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

        self.setFrameShape(QFrame.NoFrame)
        self.setLineWidth(0)
        self.setMidLineWidth(0)

        # Hard override: ignore global QSS rules that might still match #Pill
        self.setStyleSheet("QFrame#Pill{background:transparent;border:none;}")

        self._variant = variant

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 3)
        lay.setSpacing(0)

        self.label = QLabel(text)
        self.label.setObjectName("PillText")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(self.label, 1)

        self.setFixedHeight(26)

        self._restyle()

    def set_text(self, text: str):
        self.label.setText(text)

    def set_variant(self, variant: str):
        self._variant = variant
        self._restyle()

    def _restyle(self):
        # text color follows variant
        if self._variant == "success":
            self.label.setStyleSheet("color: rgba(34,197,94,0.98); font-weight: 900;")
        elif self._variant == "warn":
            self.label.setStyleSheet("color: rgba(245,197,66,0.98); font-weight: 900;")
        elif self._variant == "bad":
            self.label.setStyleSheet("color: rgba(239,68,68,0.98); font-weight: 900;")
        else:
            self.label.setStyleSheet("color: rgba(245,247,255,0.92); font-weight: 900;")
        self.update()

    def _border_color(self) -> QColor:
        # Border is what makes "black" still readable as a pill.
        if self._variant == "success":
            return QColor(34, 197, 94, int(255 * 0.65))
        if self._variant == "warn":
            return QColor(245, 197, 66, int(255 * 0.65))
        if self._variant == "bad":
            return QColor(239, 68, 68, int(255 * 0.65))
        return QColor(255, 255, 255, int(255 * 0.18))

    def paintEvent(self, event):
        # HARD FORCE: true black fill, always.
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # slight inset avoids any 1px artifacts on the widget boundary
        r = self.rect().adjusted(1, 1, -2, -2)
        radius = max(8.0, r.height() / 2.0)

        # Fill: absolute black
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawRoundedRect(r, radius, radius)

        # Subtle inner highlight (keeps it "pill" without looking grey)
        ir = r.adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawRoundedRect(ir, radius, radius)

        # Variant border
        p.setPen(QPen(self._border_color(), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, radius, radius)
