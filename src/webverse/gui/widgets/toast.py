from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, QPoint, QEvent
from PyQt5.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout, QWidget


class Toast(QFrame):
	def __init__(self, parent: QWidget):
		super().__init__(parent)
		self.setObjectName("Toast")
		self.setAttribute(Qt.WA_StyledBackground, True)
		self.setWindowFlags(Qt.SubWindow)

		self._timer = QTimer(self)
		self._timer.setSingleShot(True)
		self._timer.timeout.connect(self.hide)

		root = QHBoxLayout(self)
		root.setContentsMargins(14, 12, 14, 12)
		root.setSpacing(12)

		self._dot = QLabel("●")
		self._dot.setFixedWidth(14)
		self._dot.setAlignment(Qt.AlignTop)
		root.addWidget(self._dot)

		col = QVBoxLayout()
		col.setSpacing(2)
		root.addLayout(col, 1)

		self.title = QLabel("Success")
		self.title.setObjectName("ToastTitle")
		col.addWidget(self.title)

		self.body = QLabel("")
		self.body.setObjectName("ToastBody")
		self.body.setWordWrap(True)
		col.addWidget(self.body)

		self.hide()

	def show_toast(self, title: str, body: str, variant: str = "success", ms: int = 1700):
		self._timer.stop()
		self._pending_ms = ms

		self.setProperty("variant", variant)
		self.style().unpolish(self)
		self.style().polish(self)
		self.update()

		self.title.setText(title)
		self.body.setText(body)
		self.adjustSize()

		# Delay one tick so parent/overlay geometry is finalized (fixes first-toast clipping)
		QTimer.singleShot(0, self._deferred_show)

	def _deferred_show(self):
		self.adjustSize()
		self._position()
		self.show()
		self.raise_()
		self._timer.start(self._pending_ms)

	def _position(self):
		p = self.parentWidget()
		if not p:
			return
		margin = 18
		x = max(margin, p.width() - self.width() - margin)
		y = max(margin, p.height() - self.height() - margin)
		self.move(QPoint(x, y))


class ToastHost(QWidget):
	def __init__(self, parent: QWidget):
		super().__init__(parent)
		self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
		self.setAttribute(Qt.WA_NoSystemBackground, True)
		self.toast = Toast(self)
		self._parent = parent
		self.resize(parent.size())
		# Keep overlay sized with the parent
		parent.installEventFilter(self)
		self.show()

	def resizeEvent(self, e):
		super().resizeEvent(e)
		if self.toast.isVisible():
			self.toast._position()

	def eventFilter(self, obj, event):
		if obj is self._parent and event.type() == QEvent.Resize:
			# Overlay follows parent size so Toast._position() is correct
			self.resize(self._parent.size())
			# If a toast is up while resizing, reposition on next tick (avoids transient geometry)
			if self.toast.isVisible():
				QTimer.singleShot(0, self.toast._position)
		return super().eventFilter(obj, event)

	def show_toast(self, title: str, body: str, variant: str = "success", ms: int = 1700):
		self.toast.show_toast(title, body, variant=variant, ms=ms)

	def success(self, msg: str):
		self.show_toast("Success", msg, variant="success")

	def error(self, title: str, msg: str = "", ms: int = 2000):
		# allow either error("msg") or error("Title","Body")
		if msg == "":
			self.show_toast("Error", title, variant="error", ms=ms)
		else:
			self.show_toast(title, msg, variant="error", ms=ms)

	def warn(self, title: str, msg: str = "", ms: int = 2000):
		if msg == "":
			self.show_toast("Warning", title, variant="warn", ms=ms)
		else:
			self.show_toast(title, msg, variant="warn", ms=ms)

	def info(self, title: str, msg: str = "", ms: int = 1800):
		if msg == "":
			self.show_toast("Info", title, variant="info", ms=ms)
		else:
			self.show_toast(title, msg, variant="info", ms=ms)
