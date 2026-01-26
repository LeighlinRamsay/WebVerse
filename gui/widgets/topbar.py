# gui/widgets/topbar.py
from __future__ import annotations

from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton
)
from PyQt5.QtCore import Qt, pyqtSignal


class TopBar(QFrame):
    back_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    search_requested = pyqtSignal()
    running_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")

        self._running_lab_id = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.btn_back = QToolButton()
        self.btn_back.setObjectName("TopNavBtn")
        self.btn_back.setText("←")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.btn_back)

        self.btn_fwd = QToolButton()
        self.btn_fwd.setObjectName("TopNavBtn")
        self.btn_fwd.setText("→")
        self.btn_fwd.setCursor(Qt.PointingHandCursor)
        self.btn_fwd.clicked.connect(self.forward_requested.emit)
        layout.addWidget(self.btn_fwd)

        brand = QLabel("WebVerse")
        brand.setStyleSheet("font-size: 14px; font-weight: 950; letter-spacing: 0.6px;")
        brand.setAlignment(Qt.AlignVCenter)
        layout.addWidget(brand)

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("Search labs… (Ctrl+K)")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.search_requested.emit)
        self.search.mousePressEvent = self._search_mouse_press  # type: ignore
        self.search.setFocusPolicy(Qt.ClickFocus)
        layout.addWidget(self.search, 1)

        self.run_pill = QFrame()
        self.run_pill.setObjectName("RunPill")
        rp = QHBoxLayout(self.run_pill)
        rp.setContentsMargins(8, 6, 8, 6)
        rp.setSpacing(10)

        self.run_state = QLabel("STOPPED")
        self.run_state.setObjectName("RunState")
        self.run_state.setProperty("variant", "stopped")
        rp.addWidget(self.run_state)

        self.run_hint = QLabel("No lab running")
        self.run_hint.setObjectName("RunHint")
        rp.addWidget(self.run_hint)

        self.run_pill.setCursor(Qt.PointingHandCursor)
        self.run_pill.mousePressEvent = self._run_mouse_press  # type: ignore
        layout.addWidget(self.run_pill)

        self.set_nav_enabled(False, False)

    def _search_mouse_press(self, event):
        self.search_requested.emit()
        event.accept()

    def _run_mouse_press(self, event):
        if self._running_lab_id:
            self.running_requested.emit()
        event.accept()

    def set_nav_enabled(self, can_back: bool, can_forward: bool):
        self.btn_back.setEnabled(bool(can_back))
        self.btn_fwd.setEnabled(bool(can_forward))

    def set_running(self, lab_id: str | None, label: str | None):
        self._running_lab_id = lab_id
        if lab_id:
            self.run_state.setText("RUNNING")
            self.run_state.setProperty("variant", "running")
            self.run_hint.setText(label or "Lab running")
        else:
            self.run_state.setText("STOPPED")
            self.run_state.setProperty("variant", "stopped")
            self.run_hint.setText("No lab running")

        self.run_state.style().unpolish(self.run_state)
        self.run_state.style().polish(self.run_state)
        self.run_state.update()

    def running_lab_id(self) -> str | None:
        return self._running_lab_id
