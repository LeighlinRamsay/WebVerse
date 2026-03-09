from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import (
	QEvent,
	QPoint,
	QPointF,
	QRectF,
	Qt,
	QTimer,
	QObject,
	pyqtProperty,
	QPropertyAnimation,
)

from PyQt5.QtGui import (
	QBrush,
	QColor,
	QLinearGradient,
	QPainter,
	QPainterPath,
	QPen,
)

from PyQt5.QtWidgets import (
	QAbstractScrollArea,
	QApplication,
	QGraphicsOpacityEffect,
	QScrollBar,
	QWidget,
)

@dataclass
class OverlayScrollBarConfig:
	mode: str = "sticky"          # "sticky" | "always" | "autohide" | "hover"
	thickness: int = 12
	inset: int = 8
	radius: int = 6
	min_thumb: int = 44
	autohide_ms: int = 0          # sticky: 0; autohide/hover: e.g. 900
	wake_zone_px: int = 28        # mouse-near-edge zone that wakes it
	idle_opacity: float = 0.60    # sticky idle opacity
	fade_in_ms: int = 120
	fade_out_ms: int = 160


class OverlayScrollBar(QWidget):
	"""A fully custom-painted scrollbar overlay that syncs to a real QScrollBar.

	- Hides the native scrollbar (policy: AlwaysOff)
	- Paints a WebVerse-styled track  thumb  grip
	- Drives the underlying QScrollBar value
	- Auto-hides with a fade

	Works for any QAbstractScrollArea (QScrollArea, QTableView, QTextEdit, etc).
	"""

	def __init__(
		self,
		area: QAbstractScrollArea,
		*,
		orientation: Qt.Orientation = Qt.Vertical,
		cfg: OverlayScrollBarConfig,
		parent: Optional[QWidget] = None,
	):
		super().__init__(parent or area.viewport())
		self._area = area
		self._cfg = cfg
		self._orientation = Qt.Vertical if orientation == Qt.Vertical else Qt.Horizontal
		self._sb: QScrollBar = area.verticalScrollBar() if self._orientation == Qt.Vertical else area.horizontalScrollBar()
		self._thickness = max(6, int(cfg.thickness))
		self._inset = max(0, int(cfg.inset))
		self._radius = max(4, int(cfg.radius))
		self._min_thumb = max(18, int(cfg.min_thumb))
		self._autohide_ms = max(0, int(cfg.autohide_ms))
		self._wake_zone = max(12, int(cfg.wake_zone_px))

		self.setAttribute(Qt.WA_StyledBackground, False)
		self.setAttribute(Qt.WA_TranslucentBackground, True)
		self.setMouseTracking(True)
		self.setCursor(Qt.PointingHandCursor)
		self.setFocusPolicy(Qt.NoFocus)

		self._hover = False
		self._dragging = False
		self._drag_offset = 0.0
		self._viewport_hover_zone = False
		self._pending_relayout = False

		self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

		self._opacity = 0.0
		self._eff = QGraphicsOpacityEffect(self)
		self._eff.setOpacity(self._opacity)
		self.setGraphicsEffect(self._eff)

		self._anim = QPropertyAnimation(self, b"opacity", self)
		self._anim.setDuration(int(cfg.fade_in_ms))

		self._hide_timer = QTimer(self)
		self._hide_timer.setSingleShot(True)
		self._hide_timer.timeout.connect(self._fade_to_idle_or_hide)

		# Keep overlay positioned when the viewport resizes.
		try:
			self._area.viewport().installEventFilter(self)
			self._area.installEventFilter(self)
		except Exception:
			pass

		# Sync visual state to the real scrollbar.
		try:
			self._sb.valueChanged.connect(self._on_scroll_changed)
			self._sb.rangeChanged.connect(self._on_scroll_changed)
			self._sb.sliderPressed.connect(self._wake)
			self._sb.sliderReleased.connect(self._wake)
		except Exception:
			pass

		self._relayout()
		self._sync_visibility()
		self._init_opacity()
 
	def _init_opacity(self):
		mode = str(self._cfg.mode or "sticky").strip().lower()
		if mode == "always":
			self.opacity = 1.0
			return
		if mode == "sticky":
			self.opacity = float(self._cfg.idle_opacity)
			return
		self.opacity = 0.0

	def orientation(self) -> Qt.Orientation:
		return self._orientation

	def eventFilter(self, obj, e):
		et = e.type()
		if et in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
			# Never move the overlay while the user is dragging it; it makes
			# mouse coordinates "jump" and feels like flickering.
			if self._dragging:
				self._pending_relayout = True
			else:
				self._relayout()
				self._sync_visibility()

		elif et == QEvent.MouseMove:
			try:
				if obj is self._area.viewport():
					self._handle_viewport_mouse_move(e.pos())
			except Exception:
				pass

		elif et == QEvent.Wheel:
			# Wheel scrolling should wake the overlay.
			self._wake()
		return super().eventFilter(obj, e)

	def _handle_viewport_mouse_move(self, pos: QPoint):
		mode = str(self._cfg.mode or "sticky").strip().lower()
		if mode not in ("hover", "sticky"):
			return

		vp = self._area.viewport()
		if self._orientation == Qt.Vertical:
			in_zone = int(pos.x()) >= int(vp.width() - self._wake_zone)
		else:
			in_zone = int(pos.y()) >= int(vp.height() - self._wake_zone)

		if in_zone:
			self._viewport_hover_zone = True
			self._wake()
		else:
			self._viewport_hover_zone = False
			if mode == "hover" and (not self._dragging) and (not self._hover):
				self._hide_timer.start(140)

	def _relayout(self):
		vp = self._area.viewport()
		if self._orientation == Qt.Vertical:
			w = self._thickness
			x = max(0, vp.width() - w - self._inset)
			y = self._inset
			h = max(0, vp.height() - (self._inset * 2))
			self.setGeometry(x, y, w, h)
		else:
			h = self._thickness
			x = self._inset
			w = max(0, vp.width() - (self._inset * 2))
			y = max(0, vp.height() - h - self._inset)
			self.setGeometry(x, y, w, h)
		self.raise_()

	def _sync_visibility(self):
		# Hide when no scroll range.
		try:
			if int(self._sb.maximum()) <= int(self._sb.minimum()):
				# During a drag, never hide (some views temporarily report 0 range).
				if not self._dragging:
					self.hide()
					return
		except Exception:
			pass
		self.show()

	def _wake(self):
		if not self.isVisible():
			return

		# While dragging, keep it pinned fully visible and do NOT start timers/animations.
		if self._dragging:
			try:
				self._hide_timer.stop()
			except Exception:
				pass
			self._fade_to(1.0, immediate=True)
			return

		mode = str(self._cfg.mode or "sticky").strip().lower()
		if mode == "always":
			self.opacity = 1.0
			return

		# Wake to full visibility
		self._fade_to(1.0)

		# Then decay depending on mode
		if self._dragging:
			return
		if mode == "sticky":
			# quick settle back to idle opacity
			self._hide_timer.start(420)
		elif mode in ("autohide", "hover"):
			if self._autohide_ms > 0:
				self._hide_timer.start(self._autohide_ms)

	def _on_scroll_changed(self, *args):
		self._sync_visibility()
		self.update()
		# Avoid re-waking / re-animating on every valueChanged while dragging.
		if not self._dragging:
			self._wake()

	def _track_rect(self) -> QRectF:
		return QRectF(0.0, 0.0, float(self.width()), float(self.height()))

	def _thumb_rect(self) -> QRectF:
		track = self._track_rect()
		minv = int(self._sb.minimum())
		maxv = int(self._sb.maximum())
		val = int(self._sb.value())
		page = int(self._sb.pageStep() or 0)

		rng = max(1, (maxv - minv))
		total = float(rng + max(1, page))

		if self._orientation == Qt.Vertical:
			track_len = float(track.height())
			thumb_len = max(float(self._min_thumb), track_len * (float(max(1, page)) / total))
			thumb_len = min(track_len, thumb_len)
			usable = max(1.0, track_len - thumb_len)
			p = float(val - minv) / float(rng)
			y = track.top() + (usable * p)
			return QRectF(track.left(), y, track.width(), thumb_len)

		track_len = float(track.width())
		thumb_len = max(float(self._min_thumb), track_len * (float(max(1, page)) / total))
		thumb_len = min(track_len, thumb_len)
		usable = max(1.0, track_len - thumb_len)
		p = float(val - minv) / float(rng)
		x = track.left() + (usable * p)
		return QRectF(x, track.top(), thumb_len, track.height())

	def enterEvent(self, e):
		self._hover = True
		self._wake()
		self.update()
		return super().enterEvent(e)

	def leaveEvent(self, e):
		# If we grabbed the mouse, Qt can still deliver leave/enter while dragging.
		# Don't flip hover state while dragging (causes mode logic to fight itself).
		if not self._dragging:
			self._hover = False
		else:
			self.update()
			return super().leaveEvent(e)

		mode = str(self._cfg.mode or "sticky").strip().lower()
		if mode == "sticky":
			self._hide_timer.start(240)
		elif mode in ("autohide", "hover"):
			if self._autohide_ms > 0:
				self._hide_timer.start(180)
		self.update()
		return super().leaveEvent(e)

	def mousePressEvent(self, e):
		if e.button() != Qt.LeftButton:
			return super().mousePressEvent(e)

		try:
			if int(self._sb.maximum()) <= int(self._sb.minimum()):
				return
		except Exception:
			return

		self._wake()
		thumb = self._thumb_rect()
		pos = QPointF(e.pos())

		if thumb.contains(pos):
			self._dragging = True
			self._pending_relayout = False
			try:
				self._hide_timer.stop()
			except Exception:
				pass
			# Pin fully visible while dragging
			self._fade_to(1.0, immediate=True)
			self._drag_offset = (pos.y() - thumb.top()) if self._orientation == Qt.Vertical else (pos.x() - thumb.left())
			try:
				self.grabMouse()
			except Exception:
				pass

			e.accept()
			self.update()
			return

		# Click-to-jump (center thumb on click)
		track = self._track_rect()
		thumb_len = float(thumb.height() if self._orientation == Qt.Vertical else thumb.width())
		track_len = float(track.height() if self._orientation == Qt.Vertical else track.width())
		usable = max(1.0, track_len - thumb_len)
		coord = float(pos.y() if self._orientation == Qt.Vertical else pos.x())
		target = min(max(0.0, coord - (thumb_len / 2.0)), usable)
		p = target / usable

		minv = int(self._sb.minimum())
		maxv = int(self._sb.maximum())
		newv = int(round(minv + p * float(max(1, (maxv - minv)))))
		self._sb.setValue(newv)
		e.accept()

	def mouseMoveEvent(self, e):
		try:
			if int(self._sb.maximum()) <= int(self._sb.minimum()):
				return super().mouseMoveEvent(e)
		except Exception:
			return super().mouseMoveEvent(e)

		if not self._dragging:
			self._wake()
			return super().mouseMoveEvent(e)

		track = self._track_rect()
		thumb = self._thumb_rect()
		thumb_len = float(thumb.height() if self._orientation == Qt.Vertical else thumb.width())
		track_len = float(track.height() if self._orientation == Qt.Vertical else track.width())
		usable = max(1.0, track_len - thumb_len)

		pos = QPointF(e.pos())
		coord = float(pos.y() if self._orientation == Qt.Vertical else pos.x())
		target = coord - float(self._drag_offset)
		target = min(max(0.0, target), usable)
		p = target / usable

		minv = int(self._sb.minimum())
		maxv = int(self._sb.maximum())
		newv = int(round(minv + p * float(max(1, (maxv - minv)))))
		self._sb.setValue(newv)
		e.accept()
		self.update()

	def mouseReleaseEvent(self, e):
		if e.button() == Qt.LeftButton and self._dragging:
			self._dragging = False

			try:
				self.releaseMouse()
			except Exception:
				pass

			# Apply any delayed relayout now that coordinates are stable again.
			if self._pending_relayout:
				self._pending_relayout = False
				self._relayout()
				self._sync_visibility()

			mode = str(self._cfg.mode or "sticky").strip().lower()
			if mode == "sticky":
				self._hide_timer.start(240)
			elif mode in ("autohide", "hover"):
				if self._autohide_ms > 0:
					self._hide_timer.start(self._autohide_ms)
			e.accept()
			self.update()
			return
		return super().mouseReleaseEvent(e)

	def paintEvent(self, e):
		try:
			if int(self._sb.maximum()) <= int(self._sb.minimum()):
				return
		except Exception:
			return

		p = QPainter(self)
		p.setRenderHint(QPainter.Antialiasing, True)

		track = self._track_rect()
		thumb = self._thumb_rect()

		amber = QColor(212, 175, 55)
		amber_hot = QColor(255, 222, 140)

		active = bool(self._hover or self._dragging)

		# Track: almost invisible, but with an "amber aura" edge so it reads custom.
		track_path = QPainterPath()
		track_path.addRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), float(self._radius), float(self._radius))
		p.fillPath(track_path, QBrush(QColor(0, 0, 0, 0)))
		p.setPen(QPen(QColor(amber.red(), amber.green(), amber.blue(), 22 if active else 14), 1.0))
		p.drawPath(track_path)

		# Thumb: onyx glass with warm sheen + amber edge.
		thumb_path = QPainterPath()
		thumb_path.addRoundedRect(thumb.adjusted(0.5, 0.5, -0.5, -0.5), float(self._radius), float(self._radius))

		if self._dragging:
			edge = QColor(amber.red(), amber.green(), amber.blue(), 190)
			fill_a = 74
			fill_b = 44
		elif self._hover:
			edge = QColor(amber.red(), amber.green(), amber.blue(), 150)
			fill_a = 58
			fill_b = 34
		else:
			edge = QColor(amber.red(), amber.green(), amber.blue(), 92)
			fill_a = 30
			fill_b = 18

		grad = QLinearGradient(thumb.topLeft(), thumb.bottomRight())
		grad.setColorAt(0.0, QColor(255, 255, 255, fill_a))
		grad.setColorAt(0.55, QColor(16, 20, 28, fill_b))
		grad.setColorAt(1.0, QColor(amber.red(), amber.green(), amber.blue(), 26 if active else 18))
		p.fillPath(thumb_path, QBrush(grad))

		# Outer edge
		p.setPen(QPen(edge, 1.0))
		p.drawPath(thumb_path)

		# Inner highlight (adds "custom component" feel)
		inner = thumb.adjusted(2.0, 2.0, -2.0, -2.0)
		if inner.width() > 2 and inner.height() > 2:
			inner_path = QPainterPath()
			inner_path.addRoundedRect(inner, float(max(3, self._radius - 2)), float(max(3, self._radius - 2)))
			p.setPen(QPen(QColor(255, 255, 255, 18 if active else 12), 1.0))
			p.drawPath(inner_path)

		# Grip (3 tiny lines) so it reads like a bespoke UI control.
		p.setPen(QPen(QColor(amber_hot.red(), amber_hot.green(), amber_hot.blue(), 120 if active else 70), 1.0))
		if self._orientation == Qt.Vertical:
			cx = thumb.center().x()
			cy = thumb.center().y()
			for dy in (-4.0, 0.0, 4.0):
				p.drawLine(QPointF(cx - 2.5, cy + dy), QPointF(cx + 2.5, cy + dy))
		else:
			cx = thumb.center().x()
			cy = thumb.center().y()
			for dx in (-4.0, 0.0, 4.0):
				p.drawLine(QPointF(cx + dx, cy - 2.5), QPointF(cx + dx, cy + 2.5))

	def _fade_to(self, target: float, immediate: bool = False):
		target = max(0.0, min(1.0, float(target)))
		if immediate:
			self.opacity = target
			return
		self._anim.stop()
		cur = float(self.opacity)
		if target >= cur:
			self._anim.setDuration(int(self._cfg.fade_in_ms))
		else:
			self._anim.setDuration(int(self._cfg.fade_out_ms))
		self._anim.setStartValue(cur)
		self._anim.setEndValue(target)
		self._anim.start()

	def _fade_in(self, immediate: bool = False):
		self._fade_to(1.0, immediate=immediate)

	def _fade_out(self, immediate: bool = False):
		self._fade_to(0.0, immediate=immediate)

	def _fade_to_idle_or_hide(self):
		if not self.isVisible():
			return
		if self._dragging:
			return

		mode = str(self._cfg.mode or "sticky").strip().lower()
		if mode == "always":
			self.opacity = 1.0
			return
		if mode == "sticky":
			self._fade_to(float(self._cfg.idle_opacity))
			return
		if mode == "hover":
			# Stay visible while the cursor is in the edge wake zone.
			if self._hover or self._viewport_hover_zone:
				self._fade_to(1.0)
				return
			self._fade_to(0.0)
			return
		# autohide
		self._fade_to(0.0)

	@pyqtProperty(float)
	def opacity(self) -> float:
		return float(self._opacity)

	@opacity.setter
	def opacity(self, v: float):
		self._opacity = max(0.0, min(1.0, float(v)))
		try:
			self._eff.setOpacity(self._opacity)
		except Exception:
			pass


class OverlayScrollBarManager(QObject):
	"""Installs an application-wide event filter that attaches overlay scrollbars.

	We intentionally skip popup windows (e.g. combobox dropdowns) so we don't
	break Qt's internal item-view popups.
	"""

	def __init__(self, app: QApplication):
		super().__init__(app)
		self._app = app
		self._cfg = OverlayScrollBarConfig()
		self._vbars: "weakref.WeakKeyDictionary[QAbstractScrollArea, OverlayScrollBar]" = weakref.WeakKeyDictionary()
		self._hbars: "weakref.WeakKeyDictionary[QAbstractScrollArea, OverlayScrollBar]" = weakref.WeakKeyDictionary()
		self._scan_timer = QTimer(self)
		self._scan_timer.setSingleShot(True)
		self._scan_timer.timeout.connect(self.scan_all)

	def install(self, *, cfg: Optional[OverlayScrollBarConfig] = None):
		if cfg is not None:
			self._cfg = cfg
		try:
			self._app.installEventFilter(self)
		except Exception:
			pass
		# Delay initial scan until after widgets are constructed.
		try:
			QTimer.singleShot(0, self.scan_all)
		except Exception:
			pass
		return self

	def eventFilter(self, obj, e):
		et = e.type()
		if et in (QEvent.Show, QEvent.ChildAdded, QEvent.Polish, QEvent.LayoutRequest):
			# Coalesce scans (creating many widgets at once is common during navigation).
			if not self._scan_timer.isActive():
				self._scan_timer.start(1)
		return super().eventFilter(obj, e)

	def _is_popup(self, w: QWidget) -> bool:
		try:
			if int(w.windowFlags()) & int(Qt.Popup):
				return True
		except Exception:
			pass
		try:
			cls = str(w.window().metaObject().className() or "")
			if "QComboBoxPrivateContainer" in cls:
				return True
		except Exception:
			pass
		return False

	def _attach_one(self, area: QAbstractScrollArea):
		if not area or self._is_popup(area):
			return

		try:
			if area.property("wv_overlay_scrollbar") is False:
				return
		except Exception:
			pass

		# Avoid double-attaching.
		if area in self._vbars:
			return

		# Hide native bars. (We keep the underlying QScrollBar object for scrolling logic.)
		try:
			area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		except Exception:
			pass
		try:
			area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		except Exception:
			pass

		try:
			vb = OverlayScrollBar(area, orientation=Qt.Vertical, cfg=self._cfg)
			self._vbars[area] = vb
			vb.show()
		except Exception:
			return

		# Horizontal overlay is optional; only attach if the widget can ever need it.
		# (We still hide native horizontal bars above; this overlay will auto-hide if unused.)
		try:
			hb = OverlayScrollBar(area, orientation=Qt.Horizontal, cfg=self._cfg)
			self._hbars[area] = hb
			hb.show()
		except Exception:
			pass

	def scan_all(self):
		try:
			widgets = list(QApplication.allWidgets())
		except Exception:
			widgets = []
		for w in widgets:
			try:
				if isinstance(w, QAbstractScrollArea) and (not self._is_popup(w)):
					self._attach_one(w)
			except Exception:
				pass


def install_overlay_scrollbars(
	app: QApplication,
	*,
	mode: str = "sticky",
	thickness: int = 12,
	inset: int = 8,
	radius: int = 6,
	min_thumb: int = 44,
	autohide_ms: int = 0,
	wake_zone_px: int = 28,
	idle_opacity: float = 0.60,
	fade_in_ms: int = 120,
	fade_out_ms: int = 160,
) -> OverlayScrollBarManager:
	"""Install fully custom overlay scrollbars application-wide."""
	cfg = OverlayScrollBarConfig(
		mode=str(mode or "sticky"),
		thickness=int(thickness),
		inset=int(inset),
		radius=int(radius),
		min_thumb=int(min_thumb),
		autohide_ms=int(autohide_ms),
		wake_zone_px=int(wake_zone_px),
		idle_opacity=float(idle_opacity),
		fade_in_ms=int(fade_in_ms),
		fade_out_ms=int(fade_out_ms),
	)
	mgr = OverlayScrollBarManager(app)
	return mgr.install(cfg=cfg)
