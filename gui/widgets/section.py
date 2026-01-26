from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel

class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        t = QLabel(title)
        t.setObjectName("H2")
        row.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("Subtle")
            row.addWidget(s)

        row.addStretch()
