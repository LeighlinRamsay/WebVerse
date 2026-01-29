# gui/widgets/card.py
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel

class Card(QFrame):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        t = QLabel(title)
        t.setObjectName("H2")
        layout.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("Muted")
            s.setWordWrap(True)
            layout.addWidget(s)
