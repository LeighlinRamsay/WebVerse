from __future__ import annotations

import os
import sys
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from PyQt5.QtCore import Qt, QEvent, QTimer, QRect, QUrl, QEasingCurve, QPropertyAnimation
from PyQt5.QtGui import QColor, QPainter, QPixmap, QPainterPath, QPen
from PyQt5.QtWidgets import (
	QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
	QGraphicsDropShadowEffect, QSizePolicy, QApplication
)


def _find_repo_or_installed_sound() -> Optional[Path]:
	"""
	Find the sound file next to this module:
		webverse/gui/sounds/solve.wav

	This works in:
	- source tree (src/webverse/gui/sounds/solve.wav)
	- pip/pipx installs (site-packages/webverse/gui/sounds/solve.wav)
	"""
	try:
		# __file__ is .../webverse/gui/widgets/solve_celebration.py
		# so gui dir is parent.parent, and sounds lives under gui/sounds
		p = Path(__file__).resolve().parent.parent / "sounds" / "solve.wav"
		if p.exists() and p.is_file() and p.stat().st_size > 0:
			return p

		p_backup = Path(__file__).resolve().parent.parent / "gui" / "sounds" / "solve.wav"
		if p_backup.exists and p_backup.is_file() and p.stat().st_size > 0:
			return p
	except Exception:
		pass
	return None


def _find_packaged_sound_fs_path() -> Optional[Path]:
	"""
	Try to resolve webverse/gui/sounds/solve.wav via importlib.resources WITHOUT extracting
	or writing anywhere. This only returns a path when the resource already exists on the
	filesystem (common for pip/pipx installs).
	"""
	try:
		import importlib.resources as ir  # py3.9+

		# We expect the resource under the webverse.gui package:
		# webverse/gui/sounds/solve.wav
		res = ir.files("webverse.gui").joinpath("sounds", "solve.wav")
		if not res.is_file():
			return None

		# Only return if this resource is already a real filesystem path.
		try:
			p = Path(res)  # type: ignore[arg-type]
		except Exception:
			return None
		if p.exists() and p.is_file() and p.stat().st_size > 0:
			return p
		return None
	except Exception:
		return None


def _ensure_solve_wav() -> Optional[Path]:
	"""
	1) webverse/gui/sounds/solve.wav (repo or installed package filesystem)  [ONLY]
	2) (optional) importlib.resources filesystem path to the same asset (no extraction)

	IMPORTANT: Never reads/writes ~/.webverse/sfx. We ONLY deal with gui/sounds assets.
	"""

	p = _find_repo_or_installed_sound()
	if p:
		return p

	p = _find_packaged_sound_fs_path()
	if p:
		return p
	return None


class _SolveSound:
	def __init__(self):
		self._path = _ensure_solve_wav()
		self._effect = None
		self._qsound = None
		self._pending = False
		self._had_error = False

		self._is_linux = sys.platform.startswith("linux")

		# Precompute OS-level players (best reliability on Kali)
		self._players: List[List[str]] = []
		if self._is_linux:
			# Prefer PipeWire, then PulseAudio, then ALSA, then generic fallbacks
			if shutil.which("pw-play"):
				self._players.append(["pw-play", "{p}"])
			if shutil.which("paplay"):
				self._players.append(["paplay", "{p}"])
			if shutil.which("aplay"):
				self._players.append(["aplay", "-q", "{p}"])
			if shutil.which("play"):
				self._players.append(["play", "-q", "{p}"])
			if shutil.which("ffplay"):
				self._players.append(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{p}"])
			if shutil.which("mpv"):
				self._players.append(["mpv", "--no-video", "--really-quiet", "{p}"])

		try:
			from PyQt5.QtMultimedia import QSoundEffect  # type: ignore

			if self._path:
				eff = QSoundEffect()
				eff.setSource(QUrl.fromLocalFile(str(self._path)))
				eff.setLoopCount(1)
				eff.setVolume(0.85)

				def _on_status():
					try:
						if eff.status() == QSoundEffect.Ready and self._pending:
							self._pending = False
							eff.play()
						elif eff.status() == QSoundEffect.Error:
							self._had_error = True
					except Exception:
						self._had_error = True

				eff.statusChanged.connect(_on_status)
				self._effect = eff
		except Exception:
			self._effect = None

		try:
			from PyQt5.QtMultimedia import QSound  # type: ignore
			self._qsound = QSound
		except Exception:
			self._qsound = None

	def _spawn_os_fallback(self):
		if not self._path:
			return

		p = str(self._path)
		if self._is_linux and self._players:
			for tpl in self._players:
				try:
					cmd = [x.format(p=p) for x in tpl]
					subprocess.Popen(
						cmd,
						stdout=subprocess.DEVNULL,
						stderr=subprocess.DEVNULL,
						start_new_session=True,
					)
					return
				except Exception:
					continue

		try:
			if os.name == "nt":
				import winsound  # type: ignore
				winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
				return
		except Exception:
			pass

		try:
			subprocess.Popen(["afplay", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
			return
		except Exception:
			pass

		for cmd in (["paplay", p], ["aplay", p], ["pw-play", p]):
			try:
				subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
				return
			except Exception:
				continue

	def play(self):
		try:
			# refresh path in case resource was added after init
			if not self._path or not Path(self._path).exists():
				self._path = _ensure_solve_wav()

			# On Linux, prefer OS players first (QtMultimedia frequently fails on Kali)
			if self._is_linux and self._players and self._path:
				self._spawn_os_fallback()
				return

			if self._effect is not None and not self._had_error:
				self._pending = True
				try:
					self._effect.play()
					self._pending = False
					return
				except Exception:
					pass

				QTimer.singleShot(220, lambda: self._spawn_os_fallback() if self._pending else None)
				return

			if self._qsound is not None and self._path:
				try:
					self._qsound.play(str(self._path))
					return
				except Exception:
					pass

			self._spawn_os_fallback()
			return
		except Exception:
			pass

		try:
			QApplication.beep()
		except Exception:
			pass


@dataclass
class _Confetti:
	x: float
	y: float
	vx: float
	vy: float
	size: float
	rot: float
	vr: float
	color: QColor
	life: float
	max_life: float


class ConfettiWidget(QWidget):
	def __init__(self, parent: QWidget):
		super().__init__(parent)
		self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
		self.setAttribute(Qt.WA_StyledBackground, False)
		self._particles: List[_Confetti] = []
		self._timer = QTimer(self)
		self._timer.setInterval(16)
		self._timer.timeout.connect(self._tick)
		self._last = time.time()
		self._running = False
		self._spawn_until = 0.0
		self._spawn_rate = 26

		self._palette = [
			QColor(255, 209, 102),
			QColor(255, 180, 60),
			QColor(6, 214, 160),
			QColor(17, 138, 178),
			QColor(239, 71, 111),
			QColor(131, 56, 236),
			QColor(255, 255, 255),
		]

	def start(self, *, burst: int = 160, sustain_s: float = 3.2, sustain_rate: int = 22):
		self._particles.clear()
		self._spawn_rate = max(6, int(sustain_rate))
		self._spawn_until = time.time() + max(0.6, float(sustain_s))
		self._spawn_many(burst)

		self._last = time.time()
		self._running = True
		self._timer.start()
		self.update()

	def stop(self):
		self._running = False
		self._timer.stop()
		self._particles.clear()
		self.update()

	def _spawn_one(self):
		w = max(1, self.width())
		h = max(1, self.height())

		x = random.uniform(w * 0.08, w * 0.92)
		y = random.uniform(-h * 0.18, 0)
		vx = random.uniform(-95, 95)
		vy = random.uniform(90, 235)
		size = random.uniform(6, 14)
		rot = random.uniform(0, 360)
		vr = random.uniform(-320, 320)
		col = random.choice(self._palette)
		life = random.uniform(2.6, 4.2)
		return _Confetti(x, y, vx, vy, size, rot, vr, col, life, life)

	def _spawn_many(self, count: int):
		for _ in range(max(1, int(count))):
			self._particles.append(self._spawn_one())

	def _tick(self):
		now = time.time()
		dt = min(0.05, max(0.001, now - self._last))
		self._last = now
		if not self._running:
			return

		if now < self._spawn_until:
			self._spawn_many(self._spawn_rate)

		w = max(1, self.width())
		h = max(1, self.height())
		g = 320.0

		alive: List[_Confetti] = []
		for p in self._particles:
			p.life -= dt
			if p.life <= 0:
				continue
			p.vy += g * dt
			p.x += p.vx * dt
			p.y += p.vy * dt
			p.rot += p.vr * dt
			p.vx *= (1.0 - min(0.18 * dt, 0.02))

			if p.x < -50:
				p.x = w + 50
			elif p.x > w + 50:
				p.x = -50

			if p.y > h + 120:
				continue

			alive.append(p)

		self._particles = alive
		if (now >= self._spawn_until) and not self._particles:
			self.stop()
			return

		self.update()

	def paintEvent(self, _ev):
		if not self._particles:
			return
		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing, True)

		for p in self._particles:
			alpha = int(255 * max(0.0, min(1.0, p.life / max(0.001, p.max_life))))
			c = QColor(p.color)
			c.setAlpha(max(0, min(255, alpha)))

			painter.save()
			painter.translate(p.x, p.y)
			painter.rotate(p.rot)
			painter.setPen(Qt.NoPen)
			painter.setBrush(c)
			s = p.size
			rect = QRect(int(-s / 2), int(-s / 2), int(s), int(s))
			painter.drawRoundedRect(rect, 2, 2)
			painter.restore()


def _circle_cover(pix: QPixmap, diameter: int, ring: QColor) -> QPixmap:
	diameter = max(48, int(diameter))
	src = pix.scaled(diameter, diameter, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
	out = QPixmap(diameter, diameter)
	out.fill(Qt.transparent)

	p = QPainter(out)
	p.setRenderHint(QPainter.Antialiasing, True)

	path = QPainterPath()
	path.addEllipse(0, 0, diameter, diameter)
	p.setClipPath(path)
	p.drawPixmap(0, 0, src)
	p.setClipping(False)

	pen = QPen(ring, max(5, int(diameter * 0.03)))
	pen.setCapStyle(Qt.RoundCap)
	p.setPen(pen)
	p.setBrush(Qt.NoBrush)
	inset = int(pen.widthF() / 2) + 1
	p.drawEllipse(inset, inset, diameter - inset * 2, diameter - inset * 2)

	p.end()
	return out


class SolveCelebrationHost(QWidget):
	def __init__(self, parent: QWidget):
		super().__init__(parent)
		self.setObjectName("SolveOverlay")
		self.setWindowFlags(Qt.SubWindow)
		self.setAttribute(Qt.WA_StyledBackground, True)
		self.setVisible(False)

		self._sound = _SolveSound()

		self.setStyleSheet("""
		#SolveOverlay {
			background: qradialgradient(cx:0.5, cy:0.38, radius:1.2,
				stop:0 rgba(0,0,0,170),
				stop:0.6 rgba(0,0,0,205),
				stop:1 rgba(0,0,0,235));
		}
		#SolveCard {
			background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
				stop:0 rgba(28,30,36,245),
				stop:1 rgba(18,20,24,245));
			border: 1px solid rgba(255, 200, 90, 55);
			border-radius: 18px;
		}
		#SolveTitle {
			color: rgba(255,255,255,245);
			font-size: 28px;
			letter-spacing: 6px;
			font-weight: 700;
		}
		#SolveSubtitle {
			color: rgba(255,255,255,210);
			font-size: 16px;
			font-weight: 600;
		}
		#SolveMeta {
			color: rgba(255, 209, 102, 210);
			font-size: 13px;
			letter-spacing: 1px;
			font-weight: 700;
		}
		#SolveCover {
			background: rgba(255,255,255,10);
			border: 1px solid rgba(255,255,255,18);
			border-radius: 16px;
		}
		#SolveContinue {
			padding: 10px 22px;
			border-radius: 12px;
			background: rgba(255, 199, 95, 26);
			border: 1px solid rgba(255, 199, 95, 85);
			color: rgba(255,255,255,230);
			font-weight: 700;
		}
		#SolveContinue:hover {
			background: rgba(255, 199, 95, 36);
			border: 1px solid rgba(255, 199, 95, 120);
		}
		""")

		self.confetti = ConfettiWidget(self)

		self.card = QFrame(self)
		self.card.setObjectName("SolveCard")
		self.card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

		shadow = QGraphicsDropShadowEffect(self.card)
		shadow.setBlurRadius(40)
		shadow.setOffset(0, 18)
		shadow.setColor(QColor(0, 0, 0, 170))
		self.card.setGraphicsEffect(shadow)

		self.title = QLabel("LAB SOLVED", self.card)
		self.title.setObjectName("SolveTitle")
		self.title.setAlignment(Qt.AlignCenter)

		self.subtitle = QLabel("", self.card)
		self.subtitle.setObjectName("SolveSubtitle")
		self.subtitle.setAlignment(Qt.AlignCenter)
		self.subtitle.setWordWrap(True)

		self.image = QLabel(self.card)
		self.image.setObjectName("SolveCover")
		self.image.setAlignment(Qt.AlignCenter)
		self.image.setMinimumSize(440, 300)

		self.meta = QLabel("", self.card)
		self.meta.setObjectName("SolveMeta")
		self.meta.setAlignment(Qt.AlignCenter)

		btn_row = QHBoxLayout()
		btn_row.setSpacing(10)

		self.btn_continue = QPushButton("Continue", self.card)
		self.btn_continue.setObjectName("SolveContinue")
		self.btn_continue.clicked.connect(self.hide_overlay)

		btn_row.addStretch(1)
		btn_row.addWidget(self.btn_continue)
		btn_row.addStretch(1)

		layout = QVBoxLayout(self.card)
		layout.setContentsMargins(26, 22, 26, 22)
		layout.setSpacing(12)
		layout.addWidget(self.title)
		layout.addWidget(self.subtitle)
		layout.addWidget(self.image)
		layout.addWidget(self.meta)
		layout.addLayout(btn_row)

		self._fade = QPropertyAnimation(self, b"windowOpacity", self)
		self._fade.setDuration(220)
		self._fade.setEasingCurve(QEasingCurve.OutCubic)

		self._pop = QPropertyAnimation(self.card, b"geometry", self)
		self._pop.setDuration(260)
		self._pop.setEasingCurve(QEasingCurve.OutBack)

		self._lab_name = "Unknown Lab"

		self.installEventFilter(self)
		parent.installEventFilter(self)

	def eventFilter(self, obj, ev):
		if ev.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
			try:
				self.setGeometry(0, 0, self.parent().width(), self.parent().height())
				self.confetti.setGeometry(0, 0, self.width(), self.height())
				self._recenter_card(animate=False)
			except Exception:
				pass
		return super().eventFilter(obj, ev)

	def _recenter_card(self, *, animate: bool):
		w = self.width()
		h = self.height()

		cw = 580
		ch = 640
		if w < 640:
			cw = max(380, w - 40)
		if h < 700:
			ch = max(520, h - 40)

		target = QRect(int((w - cw) / 2), int((h - ch) / 2), int(cw), int(ch))

		if not animate:
			self.card.setGeometry(target)
			return

		start = QRect(
			target.x() + int(target.width() * 0.03),
			target.y() + int(target.height() * 0.03),
			int(target.width() * 0.94),
			int(target.height() * 0.94),
		)
		self._pop.stop()
		self._pop.setStartValue(start)
		self._pop.setEndValue(target)
		self._pop.start()

	def hide_overlay(self):
		try:
			self.confetti.stop()
		except Exception:
			pass
		self.setVisible(False)

	def mousePressEvent(self, ev):
		try:
			if not self.card.geometry().contains(ev.pos()):
				self.hide_overlay()
				return
		except Exception:
			pass
		super().mousePressEvent(ev)

	def keyPressEvent(self, ev):
		if ev.key() == Qt.Key_Escape:
			self.hide_overlay()
			return
		super().keyPressEvent(ev)

	def show_solved(self, lab, xp_awarded: Optional[int] = None):
		try:
			lab_name = getattr(lab, "name", "") or "Unknown Lab"
			diff = (getattr(lab, "difficulty", "") or "").strip()
		except Exception:
			lab_name = "Unknown Lab"
			diff = ""

		self._lab_name = lab_name

		p = None
		try:
			p = lab.image_path() if hasattr(lab, "image_path") else None
		except Exception:
			p = None
		if not p:
			try:
				lp = getattr(lab, "path", None)
				if lp:
					cand = Path(lp) / "cover.png"
					if cand.exists():
						p = cand
			except Exception:
				p = None

		pix = QPixmap()
		if p and str(p):
			try:
				pix = QPixmap(str(p))
			except Exception:
				pix = QPixmap()

		self.subtitle.setText(lab_name)

		meta_bits = []
		if diff:
			meta_bits.append(diff.upper())
		if xp_awarded is not None:
			try:
				meta_bits.append(f"+{int(xp_awarded)} XP")
			except Exception:
				pass
		self.meta.setText("  •  ".join(meta_bits))

		if not pix.isNull():
			diameter = 320
			if self.card.width() < 520:
				diameter = max(220, int(self.card.width() * 0.62))
			badge = _circle_cover(pix, diameter, QColor(255, 199, 95))
			self.image.setPixmap(badge)
			self.image.setText("")
			self.image.setMinimumHeight(max(260, diameter + 24))
		else:
			self.image.setPixmap(QPixmap())
			self.image.setText("(no cover.png)")

		self.setGeometry(0, 0, self.parent().width(), self.parent().height())
		self.confetti.setGeometry(0, 0, self.width(), self.height())
		self._recenter_card(animate=True)

		self.setWindowOpacity(0.0)
		self.setVisible(True)

		self.confetti.lower()
		self.card.raise_()

		QTimer.singleShot(35, self._sound.play)

		burst = 170
		sustain = 3.2
		rate = 22
		if diff.lower() in ("easy",):
			burst, sustain, rate = 140, 2.8, 18
		elif diff.lower() in ("medium",):
			burst, sustain, rate = 170, 3.2, 22
		elif diff.lower() in ("hard",):
			burst, sustain, rate = 210, 3.8, 26
		elif diff.lower() in ("master", "insane"):
			burst, sustain, rate = 240, 4.2, 30

		try:
			self.confetti.start(burst=burst, sustain_s=sustain, sustain_rate=rate)
		except Exception:
			pass

		try:
			self._fade.stop()
			self._fade.setStartValue(0.0)
			self._fade.setEndValue(1.0)
			self._fade.start()
		except Exception:
			self.setWindowOpacity(1.0)
