# gui/widgets/topbar.py
from __future__ import annotations

from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QToolButton,
    QGraphicsDropShadowEffect, QStyle,
)

from PyQt5.QtCore import (
    Qt, pyqtSignal, QEvent, QSize, QEasingCurve, QPropertyAnimation, QVariantAnimation, QPoint
)

from PyQt5.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient, QPen
)


class TopBar(QFrame):
    back_requested = pyqtSignal()
    forward_requested = pyqtSignal()
    search_requested = pyqtSignal()
    running_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(66)

        self._running_lab_id = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        self.btn_back = QToolButton()
        self.btn_back.setObjectName("TopNavBtn")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
        self.btn_back.setIconSize(QSize(16, 16))
        self.btn_back.setAutoRaise(True)
        self.btn_back.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.btn_back)

        self.btn_fwd = QToolButton()
        self.btn_fwd.setObjectName("TopNavBtn")
        self.btn_fwd.setCursor(Qt.PointingHandCursor)
        self.btn_fwd.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
        self.btn_fwd.setIconSize(QSize(16, 16))
        self.btn_fwd.setAutoRaise(True)
        self.btn_fwd.clicked.connect(self.forward_requested.emit)
        layout.addWidget(self.btn_fwd)

        brand = QLabel("WebVerse")
        brand.setObjectName("TopBrand")
        brand.setAlignment(Qt.AlignVCenter)
        layout.addWidget(brand)

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("Search labs…  (Ctrl+K)")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.search_requested.emit)
        self.search.mousePressEvent = self._search_mouse_press  # type: ignore
        self.search.setFocusPolicy(Qt.ClickFocus)
        self.search.installEventFilter(self)
        layout.addWidget(self.search, 1)

        # Search “scent trail” glow (only when focused)
        self._search_glow = QGraphicsDropShadowEffect(self.search)
        self._search_glow.setBlurRadius(26)
        self._search_glow.setOffset(0, 0)
        self._search_glow.setColor(QColor(255, 176, 72, 0))
        self.search.setGraphicsEffect(self._search_glow)

        self.run_pill = QFrame()
        self.run_pill.setObjectName("RunPill")
        rp = QHBoxLayout(self.run_pill)
        rp.setContentsMargins(10, 7, 10, 7)
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

        # RUNNING aura (breathing)
        self._run_shadow = QGraphicsDropShadowEffect(self.run_pill)
        self._run_shadow.setOffset(0, 0)
        self._run_shadow.setBlurRadius(18)
        self._run_shadow.setColor(QColor(42, 255, 154, 0))
        self.run_pill.setGraphicsEffect(self._run_shadow)

        self._pulse_blur = QPropertyAnimation(self._run_shadow, b"blurRadius", self)
        self._pulse_blur.setStartValue(16)
        self._pulse_blur.setEndValue(26)
        self._pulse_blur.setDuration(2800)
        self._pulse_blur.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_blur.setLoopCount(-1)

        self._pulse_alpha = QVariantAnimation(self)
        self._pulse_alpha.setStartValue(0.18)
        self._pulse_alpha.setEndValue(0.55)
        self._pulse_alpha.setDuration(2800)
        self._pulse_alpha.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_alpha.setLoopCount(-1)
        self._pulse_alpha.valueChanged.connect(self._on_pulse_alpha)

        self.set_nav_enabled(False, False)

    def _on_pulse_alpha(self, v):
        a = int(float(v) * 255)
        self._run_shadow.setColor(QColor(42, 255, 154, a))

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
            self._start_running_aura()
        else:
            self.run_state.setText("STOPPED")
            self.run_state.setProperty("variant", "stopped")
            self.run_hint.setText("No lab running")
            self._stop_running_aura()

        self.run_state.style().unpolish(self.run_state)
        self.run_state.style().polish(self.run_state)
        self.run_state.update()

        self.run_pill.style().unpolish(self.run_pill)
        self.run_pill.style().polish(self.run_pill)
        self.run_pill.update()

    def _start_running_aura(self):
        if self._pulse_blur.state() != self._pulse_blur.Running:
            self._pulse_blur.start()
        if self._pulse_alpha.state() != self._pulse_alpha.Running:
            self._pulse_alpha.start()

    def _stop_running_aura(self):
        self._pulse_blur.stop()
        self._pulse_alpha.stop()
        self._run_shadow.setBlurRadius(14)
        self._run_shadow.setColor(QColor(42, 255, 154, 0))

    def running_lab_id(self) -> str | None:
        return self._running_lab_id

    # Search glow on focus
    def eventFilter(self, obj, event):
        if obj is self.search:
            if event.type() == QEvent.FocusIn:
                self._search_glow.setColor(QColor(255, 176, 72, 95))
                self._search_glow.setBlurRadius(28)
            elif event.type() == QEvent.FocusOut:
                self._search_glow.setColor(QColor(255, 176, 72, 0))
                self._search_glow.setBlurRadius(22)
        return super().eventFilter(obj, event)

    # Glass depth + halo/vignette
    def paintEvent(self, event):
        super().paintEvent(event)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        r = self.rect()

        # Halo: center-weighted, subtle
        center = QPoint(int(r.width() * 0.46), int(r.height() * 0.55))
        halo = QRadialGradient(center, r.width() * 0.62)
        halo.setColorAt(0.0, QColor(255, 176, 72, 22))
        halo.setColorAt(0.55, QColor(255, 176, 72, 10))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, halo)

        # Vignette edges: pull attention toward center/search
        left = QLinearGradient(r.left(), 0, r.left() + 140, 0)
        left.setColorAt(0.0, QColor(0, 0, 0, 70))
        left.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(r, left)

        right = QLinearGradient(r.right() - 140, 0, r.right(), 0)
        right.setColorAt(0.0, QColor(0, 0, 0, 0))
        right.setColorAt(1.0, QColor(0, 0, 0, 70))
        p.fillRect(r, right)

        # Specular top line + bottom separator hairline
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.drawLine(r.left() + 12, r.top(), r.right() - 12, r.top())
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
