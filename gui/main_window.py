# gui/main_window.py
from __future__ import annotations

from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFrame, QShortcut, QSizePolicy, QLayout, QApplication, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox
from PyQt5.QtCore import QTimer, Qt, QSize, QEvent
from PyQt5.QtGui import QKeySequence, QIcon

from gui.theme import qss_onyx_amber
from gui.widgets.topbar import TopBar
from gui.widgets.command_palette import CommandPalette

from gui.sidebar import Sidebar
from gui.widgets.toast import ToastHost

from gui.views.home import HomeView
from gui.views.labs_browse import LabsBrowseView
from gui.views.lab_detail import LabDetailView
from gui.views.progress import ProgressView
from gui.views.settings import SettingsView


class MainWindow(QMainWindow):
    def __init__(self, state):
        super().__init__()
        self.state = state

        self.setWindowTitle("WebVerse")
        self.setWindowIcon(QIcon("gui/icons/webverse.ico"))

        # Normal top-level window WITH explicit decoration hints (KWin needs these for active maximize button).
        f = (
            Qt.Window
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinMaxButtonsHint
        )
        self.setWindowFlags(f)

        # Keep it dead-simple: a normal resizable window
        self.resize(1920, 1080)

        self._history = []  # list[(stack_index, lab_id|None)]
        self._hist_index = -1
        self._suppress_history = False

        central = QWidget()
        self.setCentralWidget(central)

        # Global focus sink (so inputs drop :focus when clicking anywhere else)
        self._focus_sink = QWidget(central)
        self._focus_sink.setObjectName("FocusSink")
        self._focus_sink.setFocusPolicy(Qt.StrongFocus)
        self._focus_sink.setFixedSize(1, 1)
        self._focus_sink.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._focus_sink.move(0, 0)

        QApplication.instance().installEventFilter(self)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Make sure the root is not “fixed”
        central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.topbar = TopBar()
        root.addWidget(self.topbar)

        body = QFrame()
        body.setObjectName("AppShell")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(14, 14, 14, 14)
        body_layout.setSpacing(12)
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.home = HomeView(state)
        self.browse = LabsBrowseView(state)
        self.lab_detail = LabDetailView(state)
        self.progress = ProgressView(state)
        self.settings = SettingsView(state)

        self.stack.addWidget(self.home)       # 0
        self.stack.addWidget(self.browse)     # 1
        self.stack.addWidget(self.lab_detail) # 2
        self.stack.addWidget(self.progress)   # 3
        self.stack.addWidget(self.settings)   # 4

        # Let Progress jump into a lab detail page on row click
        if hasattr(self.progress, "lab_selected"):
            try:
                self.progress.lab_selected.connect(self._select_and_open_lab)
            except Exception:
                pass

        self.sidebar = Sidebar(self.stack)

        # Global toast host overlay
        self.toast_host = ToastHost(self)
        self.toast_host.raise_()


        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.stack, 1)
        root.addWidget(body, 1)

        self.setStyleSheet(qss_onyx_amber())

        self.palette = CommandPalette(state, self)
        self.palette.lab_selected.connect(self._select_and_open_lab)

        self.shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_palette.activated.connect(self._open_palette)

        self.topbar.back_requested.connect(self._go_back)
        self.topbar.forward_requested.connect(self._go_forward)
        self.topbar.search_requested.connect(self._open_palette)
        self.topbar.running_requested.connect(self._open_running_lab)

        self.lab_detail.nav_back.connect(self._go_back)
        self.lab_detail.nav_forward.connect(self._go_forward)
        self.lab_detail.nav_to_labs.connect(lambda: self.navigate(1, push=True))

        self.state.running_changed.connect(self._update_running_pill)
        self._update_running_pill(self.state.running())

        self.state.docker_changed.connect(lambda text, kind: self.sidebar.set_docker_status(text, kind))
        text, kind = self.state.docker_status()
        self.sidebar.set_docker_status(text, kind)

        self.home.nav_labs.connect(lambda: self.navigate(1, push=True))
        self.home.request_select_lab.connect(self._select_and_open_lab)
        self.browse.request_open_lab.connect(self._select_and_open_lab)

        self.stack.currentChanged.connect(self._on_stack_changed)

        self.navigate(0, push=True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.state.refresh_docker)
        self.timer.start(12000)

    def _post_show_unlock_and_audit(self):
        """
        Runs after the native window exists.
        1) Force-unlock resizing hints on the main window  core containers.
        2) Print offenders that would disable maximize (fixed min=max, SetFixedSize layouts, etc).
        """
        # ---- 1) Force-unlock top-level sizing ----
        try:
            self.setMinimumSize(QSize(0, 0))
            self.setMaximumSize(QSize(16777215, 16777215))
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        cw = self.centralWidget()
        if cw:
            try:
                cw.setMinimumSize(QSize(0, 0))
                cw.setMaximumSize(QSize(16777215, 16777215))
                cw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            except Exception:
                pass

        for w in (getattr(self, "stack", None),):
            if w:
                try:
                    w.setMinimumSize(QSize(0, 0))
                    w.setMaximumSize(QSize(16777215, 16777215))
                    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                except Exception:
                    pass

        # ---- 2) Audit widget tree for “maximize killers” ----
        offenders = []

        def check_widget(widget: QWidget):
            try:
                mn = widget.minimumSize()
                mx = widget.maximumSize()
                fixed = (mn.width() == mx.width()) and (mn.height() == mx.height()) and (mn.width() > 0) and (mn.height() > 0)
                if fixed:
                    offenders.append(("FIXED_WIDGET", widget, mn, mx))
                # suspicious max size (someone set maximumSize to something small)
                if (mx.width() < 16777215 or mx.height() < 16777215) and not fixed:
                    offenders.append(("MAX_LIMIT", widget, mn, mx))
            except Exception:
                pass

            lay = widget.layout()
            if lay is not None:
                try:
                    if lay.sizeConstraint() == QLayout.SetFixedSize:
                        offenders.append(("FIXED_LAYOUT", widget, None, None))
                except Exception:
                    pass

        check_widget(self)
        if cw:
            check_widget(cw)
            for child in cw.findChildren(QWidget):
                check_widget(child)

        print("\n--- RESIZE AUDIT ---")
        print("window min:", self.minimumSize().width(), self.minimumSize().height())
        print("window max:", self.maximumSize().width(), self.maximumSize().height())
        print("fixed?:", self.minimumSize() == self.maximumSize())
        for kind, widget, mn, mx in offenders[:80]:
            name = widget.objectName() or widget.__class__.__name__
            if kind == "FIXED_LAYOUT":
                print(f"[{kind}] {name} -> layout.sizeConstraint == SetFixedSize")
            else:
                print(f"[{kind}] {name} -> min={mn.width()}x{mn.height()} max={mx.width()}x{mx.height()}")
        print("--- END AUDIT ---\n")

    def show_toast(self, message, level="info", timeout=3000):
        self.toast_host.show_toast(message, level, timeout)

    def toast_success(self, msg):
        self.show_toast(msg, "success")

    def toast_error(self, msg):
        self.show_toast(msg, "error")

    def toast_warn(self, msg):
        self.show_toast(msg, "warn")

    def _open_palette(self):
        self.palette.open_centered()

    def _update_running_pill(self, lab):
        if lab:
            label = f"{lab.name}  •  click to open"
            self.topbar.set_running(lab.id, label)
        else:
            self.topbar.set_running(None, None)

    def _open_running_lab(self):
        lab = self.state.running()
        if lab:
            self._select_and_open_lab(lab.id)

    def _on_stack_changed(self, index: int):
        if self._suppress_history:
            return

        lab_id = None
        if index == 2 and self.state.selected():
            lab_id = self.state.selected().id

        self._push_history(index, lab_id)

    def _push_history(self, stack_index: int, lab_id: str | None):
        if self._hist_index < len(self._history) - 1:
            self._history = self._history[: self._hist_index + 1]

        if self._history and self._history[-1] == (stack_index, lab_id):
            self._hist_index = len(self._history) - 1
            self._update_nav_buttons()
            return

        self._history.append((stack_index, lab_id))
        self._hist_index = len(self._history) - 1
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        can_back = self._hist_index > 0
        can_fwd = self._hist_index < (len(self._history) - 1)
        self.topbar.set_nav_enabled(can_back, can_fwd)

        if hasattr(self.lab_detail, "btn_back"):
            self.lab_detail.btn_back.setEnabled(can_back)
        if hasattr(self.lab_detail, "btn_fwd"):
            self.lab_detail.btn_fwd.setEnabled(can_fwd)

    def _go_back(self):
        if self._hist_index <= 0:
            return
        self._hist_index -= 1
        stack_index, lab_id = self._history[self._hist_index]
        self.navigate(stack_index, lab_id=lab_id, push=False)

    def _go_forward(self):
        if self._hist_index >= len(self._history) - 1:
            return
        self._hist_index += 1
        stack_index, lab_id = self._history[self._hist_index]
        self.navigate(stack_index, lab_id=lab_id, push=False)

    def navigate(self, stack_index: int, lab_id: str | None = None, push: bool = True):
        self._suppress_history = True
        try:
            if stack_index == 2 and lab_id:
                self._select_lab_only(lab_id)
                self.sidebar.set_page(2)
            else:
                self.sidebar.set_page(stack_index)
        finally:
            self._suppress_history = False

        if push:
            self._push_history(stack_index, lab_id)

        self._update_nav_buttons()

    def _select_lab_only(self, lab_id: str):
        lab = next((x for x in self.state.labs() if x.id == lab_id), None)
        if lab:
            self.state.set_selected(lab)
            self.lab_detail.set_lab(lab)

    def _select_and_open_lab(self, lab_id: str):
        self._select_lab_only(lab_id)
        self.navigate(2, lab_id=lab_id, push=True)

    def _ancestor_is_input(self, obj) -> bool:
        w = obj
        while w is not None:
            if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox)):
                return True
            w = w.parent()
        return False

    def _sink_focus(self):
        fw = QApplication.focusWidget()

        # close combo popup if the focused widget is a combo
        if isinstance(fw, QComboBox):
            try:
                if fw.view() and fw.view().isVisible():
                    fw.hidePopup()
            except Exception:
                pass

        self._focus_sink.setFocus(Qt.MouseFocusReason)

    def closeEvent(self, event):
        # Ensure lab notes are persisted even if the user closes immediately.
        try:
            if hasattr(self, "lab_detail") and hasattr(self.lab_detail, "flush_notes"):
                self.lab_detail.flush_notes()
        except Exception:
            pass
        return super().closeEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            fw = QApplication.focusWidget()

            # only do anything if an input currently has focus
            if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox)):
                # If a popup (combo/menu/etc) is open and we clicked inside it, don't sink focus.
                popup = QApplication.activePopupWidget()
                if popup is not None:
                    gp = event.globalPos()
                    if popup.rect().contains(popup.mapFromGlobal(gp)):
                        return super().eventFilter(obj, event)

                # If we clicked an input (or inside one), don't sink focus.
                if self._ancestor_is_input(obj):
                    return super().eventFilter(obj, event)

                # Otherwise: click-away => sink focus (this covers Sidebar/TopBar too)
                self._sink_focus()

        return super().eventFilter(obj, event)
