# gui/main.py
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer

from webverse.gui.main_window import MainWindow
from webverse.gui.app_state import AppState

def run():
    app = QApplication(sys.argv)
    state = AppState()
    w = MainWindow(state)
    QTimer.singleShot(0, w.show)
    sys.exit(app.exec_())

# Backwards-compatible entrypoint (apiverse.py imports start)
def start():
    run()
