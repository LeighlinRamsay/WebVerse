# gui/widgets/pill.py
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel


class Pill(QFrame):
    """
    Small status pill used inside tables/cards.
    Variants: success | warn | bad | muted
    """

    def __init__(self, text: str, variant: str = "muted", parent=None):
        super().__init__(parent)
        self.setObjectName("Pill")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("variant", variant)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 3)
        lay.setSpacing(0)

        self.label = QLabel(text)
        self.label.setObjectName("PillText")
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label, 1)

        self.setFixedHeight(26)

        self._restyle()

    def set_text(self, text: str):
        self.label.setText(text)

    def set_variant(self, variant: str):
        self.setProperty("variant", variant)
        self._restyle()

    def _restyle(self):
        # forces QSS refresh
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
