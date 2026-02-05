# gui/sidebar.py
from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt


class _NavButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("NavButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("active", False)

    def set_active(self, active: bool):
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class Sidebar(QFrame):
    def __init__(self, stack, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.stack = stack

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.buttons = [
            _NavButton("Home"),
            _NavButton("Browse Labs"),
            _NavButton("Progress"),
            _NavButton("Settings"),
        ]

        page_for_button = [0, 1, 3, 4]  # Home, Browse, Progress, Settings -> stack index
        for i, btn in enumerate(self.buttons):
            btn.clicked.connect(lambda _, x=i: self.set_page(page_for_button[x]))
            layout.addWidget(btn)

        layout.addStretch(1)

        self.docker_badge = QFrame()
        self.docker_badge.setObjectName("DockerBadge")
        bl = QHBoxLayout(self.docker_badge)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.setSpacing(8)

        self.docker_text = QLabel("Docker: —")
        self.docker_text.setObjectName("DockerBadgeText")
        bl.addWidget(self.docker_text)

        layout.addWidget(self.docker_badge)

        self.set_page(0)

    def set_page(self, index: int):
        # index is the STACK index (not the button index)
        self.stack.setCurrentIndex(index)

        # Active state is based on "context"
        # Home -> 0
        # Browse Labs list -> 1
        # Lab detail -> 2 (NO sidebar selection)
        # Progress -> 3
        # Settings -> 4
        active_btn = None
        if index == 0:
            active_btn = 0
        elif index == 1:
            active_btn = 1
        elif index == 3:
            active_btn = 2
        elif index == 4:
            active_btn = 3

        for i, btn in enumerate(self.buttons):
            btn.set_active(active_btn is not None and i == active_btn)

    def set_docker_status(self, text: str, kind: str = "neutral"):
        palette = {
            "ok": ("rgba(34,197,94,0.14)", "rgba(34,197,94,0.30)"),
            "warn": ("rgba(245,158,11,0.14)", "rgba(245,158,11,0.30)"),
            "bad": ("rgba(239,68,68,0.14)", "rgba(239,68,68,0.30)"),
            "neutral": ("rgba(16,20,28,0.55)", "rgba(255,255,255,0.08)"),
        }
        bg, bd = palette.get(kind, palette["neutral"])
        self.docker_badge.setStyleSheet(
            f"QFrame#DockerBadge {{ background: {bg}; border: 1px solid {bd}; }}"
        )
        self.docker_text.setText(text)
