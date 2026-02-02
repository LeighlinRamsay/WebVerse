# gui/main.py
import sys
import signal
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer

from webverse.gui.main_window import MainWindow
from webverse.gui.app_state import AppState

def run():
	app = QApplication(sys.argv)
	state = AppState()
	w = MainWindow(state)

	# ---- Anonymous telemetry (best-effort) ----
	# Records first_seen / last_seen (heartbeats) / last_closed_app.
	try:
		from webverse.core.usercounter import send_app_first_seen, send_app_seen, send_app_closed

		# first_seen only once per device
		send_app_first_seen()

		# last_seen on startup + periodic heartbeat while running
		send_app_seen()
		_hb = QTimer()
		_hb.setInterval(60_000)  # 60s
		_hb.timeout.connect(send_app_seen)
		_hb.start()

		# last_closed_app on exit
		app.aboutToQuit.connect(send_app_closed)

		# Ensure close telemetry fires on Ctrl+C / SIGTERM too.
		# NOTE: send_app_closed() is synchronous now, so it will flush before quitting.
		def _handle_signal(signum, frame):
			try:
				send_app_closed()
			except Exception:
				pass
			QTimer.singleShot(0, app.quit)

		for _sig in (signal.SIGINT, signal.SIGTERM):
			try:
				signal.signal(_sig, _handle_signal)
			except Exception:
				pass

	except Exception:
		pass


	QTimer.singleShot(0, w.show)
	sys.exit(app.exec_())

# Backwards-compatible entrypoint (apiverse.py imports start)
def start():
	run()
