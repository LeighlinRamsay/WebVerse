from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt

class StatTile(QFrame):
    def __init__(self, label: str, value: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("StatTile")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        v = QLabel(value)
        v.setAlignment(Qt.AlignLeft)
        v.setStyleSheet("font-size: 22px; font-weight: 850;")
        layout.addWidget(v)

        l = QLabel(label)
        l.setObjectName("Muted")
        layout.addWidget(l)

        if hint:
            h = QLabel(hint)
            h.setObjectName("Subtle")
            h.setWordWrap(True)
            layout.addWidget(h)
