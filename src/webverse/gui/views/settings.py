from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from typing import Optional, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QMessageBox,
    QScrollArea,
)

from webverse.core.docker_ops import docker_available

class SettingsView(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        # Important on Linux: ensure this page never clamps max size.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._docker_ok: Optional[bool] = None
        self._docker_msg: str = "Unknown"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)


        scroll = QScrollArea()
        scroll.setObjectName("SettingsScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        surface = QFrame()
        surface.setObjectName("ContentSurface")
        surface.setAttribute(Qt.WA_StyledBackground, True)
        surface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # IMPORTANT: this prevents “surface” from trying to be wider than the viewport
        surface.setMinimumWidth(0)

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("H1")
        layout.addWidget(title)

        subtitle = QLabel("Ops console, environment health, and quick links. Stored locally.")
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)

        # ---- Top row: Profile + Quick Ops ----
        top = QHBoxLayout()
        top.setSpacing(12)
        layout.addLayout(top)

        self.profile = QFrame()
        self.profile.setObjectName("OpsCard")
        self.profile.setAttribute(Qt.WA_StyledBackground, True)
        self.profile.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self.profile, 1)

        pl = QHBoxLayout(self.profile)
        pl.setContentsMargins(14, 14, 14, 14)
        pl.setSpacing(12)

        badge = QLabel("⚙")
        badge.setObjectName("OpsBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(54, 54)
        pl.addWidget(badge, 0, Qt.AlignTop)

        pcol = QVBoxLayout()
        pcol.setSpacing(4)
        pl.addLayout(pcol, 1)

        self.profile_title = QLabel("WebVerse Console")
        self.profile_title.setObjectName("OpsTitle")
        pcol.addWidget(self.profile_title)

        self.profile_sub = QLabel("Health checks, runtime actions, and docs.")
        self.profile_sub.setObjectName("Muted")
        self.profile_sub.setWordWrap(True)
        pcol.addWidget(self.profile_sub)

        self.ops = QFrame()
        self.ops.setObjectName("OpsCard")
        self.ops.setAttribute(Qt.WA_StyledBackground, True)
        self.ops.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self.ops, 1)

        ol = QVBoxLayout(self.ops)
        ol.setContentsMargins(14, 14, 14, 14)
        ol.setSpacing(10)

        ops_title = QLabel("Quick Ops")
        ops_title.setObjectName("H2")
        ol.addWidget(ops_title)

        ops_hint = QLabel("Fast actions you’ll actually use. Safe and local.")
        ops_hint.setObjectName("Muted")
        ops_hint.setWordWrap(True)
        ol.addWidget(ops_hint)

        ops_row = QHBoxLayout()
        ops_row.setSpacing(10)
        ol.addLayout(ops_row)

        self.btn_open_docker = self._pill_btn("Open Docker Docs", "ghost")
        self.btn_open_docker.clicked.connect(lambda: webbrowser.open("https://docs.docker.com/get-docker/"))
        ops_row.addWidget(self.btn_open_docker, 0, Qt.AlignLeft)

        self.btn_view_logs = self._pill_btn("Open Project Folder", "ghost")
        self.btn_view_logs.clicked.connect(self._open_project_folder)
        ops_row.addWidget(self.btn_view_logs, 0, Qt.AlignLeft)

        ops_row.addStretch(1)

        self.btn_recheck = self._pill_btn("Re-check Docker", "primary")
        self.btn_recheck.clicked.connect(self._check_docker)
        ops_row.addWidget(self.btn_recheck, 0, Qt.AlignRight)

        # ---- Stats row ----
        stats = QHBoxLayout()
        stats.setSpacing(12)
        layout.addLayout(stats)

        self.stat_docker = self._stat_card("Docker", "Unknown")
        self.stat_runtime = self._stat_card("Runtime", "STOPPED")
        self.stat_active = self._stat_card("Active Lab", "—")
        self.stat_hint = self._stat_card("Tip", "Use Ctrl+K")
        for w in (self.stat_docker, self.stat_runtime, self.stat_active, self.stat_hint):
            stats.addWidget(w, 1)

        # ---- Health section ----
        health = QFrame()
        health.setObjectName("SettingsPanel")
        health.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(health)
        hl.setContentsMargins(14, 14, 14, 14)
        hl.setSpacing(10)

        htitle = QLabel("Environment Health")
        htitle.setObjectName("H2")
        hl.addWidget(htitle)

        hhint = QLabel("These checks mirror what the app needs to run labs reliably.")
        hhint.setObjectName("Muted")
        hhint.setWordWrap(True)
        hl.addWidget(hhint)

        self.docker_row = self._health_row(
            title="Docker Engine",
            subtitle="Required to start labs",
            status="Checking…",
            variant="neutral",
        )
        hl.addWidget(self.docker_row)

        self.running_row = self._health_row(
            title="Lab Runtime",
            subtitle="Detects what you currently have running",
            status="—",
            variant="neutral",
        )
        hl.addWidget(self.running_row)

        # ---- Links section ----
        links = QFrame()
        links.setObjectName("SettingsPanel")
        links.setAttribute(Qt.WA_StyledBackground, True)
        ll = QVBoxLayout(links)
        ll.setContentsMargins(14, 14, 14, 14)
        ll.setSpacing(10)

        ltitle = QLabel("Docs & Shortcuts")
        ltitle.setObjectName("H2")
        ll.addWidget(ltitle)

        lhint = QLabel("Stuff you’ll click when something breaks.")
        lhint.setObjectName("Muted")
        lhint.setWordWrap(True)
        ll.addWidget(lhint)

        grid = QHBoxLayout()
        grid.setSpacing(12)
        ll.addLayout(grid)

        left_links = QVBoxLayout()
        left_links.setSpacing(10)
        grid.addLayout(left_links, 1)

        right_links = QVBoxLayout()
        right_links.setSpacing(10)
        grid.addLayout(right_links, 1)

        left_links.addWidget(self._link_card(
            "Docker Install",
            "Get Docker Desktop / Engine set up.",
            "Open",
            lambda: webbrowser.open("https://docs.docker.com/get-docker/"),
        ))
        left_links.addWidget(self._link_card(
            "Docker Troubleshooting",
            "Common daemon + permission issues.",
            "Open",
            lambda: webbrowser.open("https://docs.docker.com/config/daemon/"),
        ))

        right_links.addWidget(self._link_card(
            "WebVerse Repo",
            "Open the project folder on disk.",
            "Open",
            self._open_project_folder,
        ))
        right_links.addWidget(self._link_card(
            "Keyboard Shortcuts",
            "Ctrl+K opens the command palette.",
            "Copy",
            lambda: self._copy_text("Ctrl+K — Command Palette"),
        ))

        layout.addWidget(health)
        layout.addWidget(links)

        # CRITICAL: Give the page an infinitely expandable vertical item.
        # Without this, a stack of “Fixed” sections can clamp the page max height,
        # which disables the window maximize button on Linux WMs.
        layout.addStretch(1)

        scroll.setWidget(surface)
        outer.addWidget(scroll, 1)

        # Live updates (runtime + docker info already exists in AppState)
        if hasattr(self.state, "docker_changed"):
            self.state.docker_changed.connect(lambda text, kind: self._apply_docker_from_state(text, kind))
        if hasattr(self.state, "running_changed"):
            self.state.running_changed.connect(lambda _lab: self._apply_runtime_from_state())
 

        # Initial render
        self._apply_runtime_from_state()
        self._check_docker()

        # Periodic refresh (keeps it feeling "alive")
        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self._apply_runtime_from_state)
        self._pulse.start(2000)

    # ---- UI builders ----
    def _pill_btn(self, text: str, kind: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setCheckable(False)
        if kind == "primary":
            b.setObjectName("PrimaryButton")
        else:
            b.setObjectName("GhostButton")
        return b

    
    def _stat_card(self, label: str, value: str) -> QFrame:
        f = QFrame()
        f.setObjectName("StatCard")
        f.setAttribute(Qt.WA_StyledBackground, True)
        f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        l = QVBoxLayout(f)
        l.setContentsMargins(14, 12, 14, 12)
        l.setSpacing(2)

        v = QLabel(value)
        v.setObjectName("StatValue")
        l.addWidget(v)

        t = QLabel(label)
        t.setObjectName("StatLabel")
        l.addWidget(t)

        f._value_label = v
        return f

    def _health_row(self, title: str, subtitle: str, status: str, variant: str = "neutral") -> QFrame:
        row = QFrame()
        row.setObjectName("HealthRow")
        row.setAttribute(Qt.WA_StyledBackground, True)

        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(12)

        dot = QLabel("●")
        dot.setObjectName("HealthDot")
        dot.setProperty("variant", variant)
        rl.addWidget(dot, 0, Qt.AlignTop)

        mid = QVBoxLayout()
        mid.setSpacing(4)
        rl.addLayout(mid, 1)

        t = QLabel(title)
        t.setObjectName("HealthTitle")
        mid.addWidget(t)

        sub = QLabel(subtitle)
        sub.setObjectName("HealthMeta")
        sub.setWordWrap(True)
        mid.addWidget(sub)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        right.setSpacing(6)
        rl.addLayout(right, 0)

        pill = QLabel(status)
        pill.setObjectName("HealthPill")
        pill.setProperty("variant", variant)
        pill.setAlignment(Qt.AlignCenter)
        right.addWidget(pill, 0, Qt.AlignRight)

        row._dot = dot
        row._pill = pill
        row._sub = sub
        row._title = t
        return row

    def _link_card(self, title: str, subtitle: str, cta: str, fn) -> QFrame:
        c = QFrame()
        c.setObjectName("LinkCard")
        c.setAttribute(Qt.WA_StyledBackground, True)

        l = QHBoxLayout(c)
        l.setContentsMargins(14, 12, 14, 12)
        l.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(4)
        l.addLayout(left, 1)

        t = QLabel(title)
        t.setObjectName("LinkTitle")
        left.addWidget(t)

        s = QLabel(subtitle)
        s.setObjectName("LinkMeta")
        s.setWordWrap(True)
        left.addWidget(s)

        b = QPushButton(cta)
        b.setObjectName("GhostButton")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        l.addWidget(b, 0, Qt.AlignRight)

        return c

    # ---- Behaviors ----
    def _apply_docker_from_state(self, text: str, kind: str) -> None:
        # text looks like "Docker Version: 28.5.1" or "Docker Version: Unavailable (...)"
        ok = (kind == "ok")
        msg = text.replace("Docker Version:", "").strip()
        self._set_docker(ok, msg)

    def _check_docker(self):
        ok, msg = docker_available()
        self._set_docker(ok, msg)
        if not ok:
            QMessageBox.warning(self, "Docker not ready", msg)

    def _set_docker(self, ok: bool, msg: str) -> None:
        self._docker_ok = bool(ok)
        self._docker_msg = (msg or "").strip() or "Unknown"

        # Stat card
        self.stat_docker._value_label.setText("READY" if ok else "MISSING")

        # Health row
        variant = "success" if ok else "error"
        self.docker_row._dot.setProperty("variant", variant)
        self.docker_row._pill.setProperty("variant", variant)
        self.docker_row._pill.setText("OK" if ok else "NOT READY")
        self.docker_row._sub.setText(self._docker_msg)
        self.docker_row.style().unpolish(self.docker_row)
        self.docker_row.style().polish(self.docker_row)
        self.docker_row.update()

    def _apply_runtime_from_state(self) -> None:
        lab = None
        try:
            lab = self.state.running() if hasattr(self.state, "running") else None
        except Exception:
            lab = None

        if lab:
            self.stat_runtime._value_label.setText("RUNNING")
            self.stat_active._value_label.setText(getattr(lab, "name", "—"))

            self.running_row._dot.setProperty("variant", "success")
            self.running_row._pill.setProperty("variant", "success")
            self.running_row._pill.setText("RUNNING")
            self.running_row._sub.setText(f"{getattr(lab, 'name', 'Lab')}  •  id: {getattr(lab, 'id', '')}")
        else:
            self.stat_runtime._value_label.setText("STOPPED")
            self.stat_active._value_label.setText("—")

            self.running_row._dot.setProperty("variant", "neutral")
            self.running_row._pill.setProperty("variant", "neutral")
            self.running_row._pill.setText("IDLE")
            self.running_row._sub.setText("No lab is currently running.")

        self.running_row.style().unpolish(self.running_row)
        self.running_row.style().polish(self.running_row)
        self.running_row.update()

    def _open_project_folder(self):
        # Opens current working directory in file manager (Linux friendly).
        try:
            import os
            import subprocess
            subprocess.Popen(["xdg-open", os.getcwd()])
        except Exception:
            # fallback: open in browser-ish way
            try:
                import pathlib
                webbrowser.open(pathlib.Path(os.getcwd()).as_uri())
            except Exception:
                pass

    def _copy_text(self, text: str) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
        except Exception:
            pass
