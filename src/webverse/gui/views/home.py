# gui/views/home.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QEvent, QTimer, QRect, QEasingCurve, QPropertyAnimation, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap

from PyQt5.QtWidgets import (
	QWidget,
	QVBoxLayout,
	QHBoxLayout,
	QGridLayout,
	QLabel,
	QFrame,
	QSizePolicy,
	QPushButton,
	QScrollArea,
	QGraphicsDropShadowEffect,
	QScroller,
	QScrollerProperties,
)

from webverse.core import progress_db

from webverse.core.ranks import solved_count as _solved_count, completion_percent as _completion_percent
from webverse.core.runtime import get_running_lab
from webverse.core.xp import base_xp_for_difficulty
from webverse.gui.util_avatar import lab_badge_icon, lab_circle_icon

# Keep in sync with api-opensource/auth.py rank tiers
_RANK_TIERS = [
	(0, "Recruit"),
	(500, "Operator"),
	(1500, "Specialist"),
	(3500, "Veteran"),
	(7000, "Elite"),
	(12000, "Legend"),
]

_DIFF_ORDER = {
	"easy": 0,
	"medium": 1,
	"hard": 2,
	"master": 3,
}


class _XPBar(QFrame):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setObjectName("XPBar")
		self.setAttribute(Qt.WA_StyledBackground, True)
		self._fill = QFrame(self)
		self._fill.setObjectName("XPFill")
		self._fill.setAttribute(Qt.WA_StyledBackground, True)
		self._frac = 0.0

	def set_fraction(self, frac: float):
		try:
			self._frac = max(0.0, min(1.0, float(frac)))
		except Exception:
			self._frac = 0.0
		self._relayout()

	def resizeEvent(self, e):
		super().resizeEvent(e)
		self._relayout()

	def _relayout(self):
		w = self.width()
		h = self.height()
		fw = int(w * self._frac)
		self._fill.setGeometry(0, 0, fw, h)


def _emblem(text: str, size: int = 54) -> QPixmap:
	pm = QPixmap(size, size)
	pm.fill(Qt.transparent)
	p = QPainter(pm)
	p.setRenderHint(QPainter.Antialiasing, True)
	ring = QColor(245, 197, 66, 220)
	pen = QPen(ring)
	pen.setWidth(3)
	p.setPen(pen)
	p.setBrush(QColor(16, 20, 28, 220))
	p.drawEllipse(3, 3, size - 6, size - 6)
	p.setPen(Qt.NoPen)
	p.setBrush(QColor(245, 197, 66, 60))
	p.drawEllipse(10, 10, size - 20, size - 20)
	p.setPen(QColor(245, 247, 255, 235))
	f = QFont("Inter", max(10, int(size * 0.28)))
	f.setBold(True)
	p.setFont(f)
	p.drawText(pm.rect(), Qt.AlignCenter, text)
	p.end()
	return pm

def _accent_for_difficulty(key: str) -> Tuple[int, int, int]:
	return {
		"easy": (36, 214, 115),
		"medium": (245, 197, 66),
		"hard": (255, 82, 82),
		"master": (168, 107, 255),
	}.get((key or "").lower(), (122, 132, 154))


def _rgba(rgb: Tuple[int, int, int], alpha: int) -> str:
	return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})"


class _HoverCard(QFrame):
	def __init__(self, parent=None):
		super().__init__(parent)
		self._difficulty_key = "neutral"
		self._base_rect = QRect()
		self._lift_px = 6

		self._anim = QPropertyAnimation(self, b"geometry", self)
		self._anim.setDuration(140)
		self._anim.setEasingCurve(QEasingCurve.OutCubic)

		self._shadow = QGraphicsDropShadowEffect(self)
		self._shadow.setBlurRadius(24)
		self._shadow.setOffset(0, 12)
		self._shadow.setColor(QColor(0, 0, 0, 155))
		self.setGraphicsEffect(self._shadow)

		self.setProperty("hovered", False)

	def set_base_geometry(self, rect: QRect) -> None:
		self._base_rect = QRect(rect)
		if not bool(self.property("hovered")):
			self.setGeometry(self._base_rect)
		else:
			hover_rect = QRect(self._base_rect)
			hover_rect.translate(0, -self._lift_px)
			self.setGeometry(hover_rect)

	def set_difficulty_key(self, key: str) -> None:
		self._difficulty_key = (key or "neutral").lower()
		self._apply_visual_state()

	def _apply_visual_state(self) -> None:
		hovered = bool(self.property("hovered"))
		accent = _accent_for_difficulty(self._difficulty_key)

		border = _rgba(accent, 165 if hovered else 88)
		state_glow = _rgba(accent, 18 if hovered else 8)
		badge_bg = _rgba(accent, 34 if hovered else 24)
		badge_border = _rgba(accent, 150 if hovered else 108)
		button_top = _rgba(accent, 64 if hovered else 46)
		button_bottom = _rgba(accent, 30 if hovered else 18)

		self._shadow.setBlurRadius(36 if hovered else 24)
		self._shadow.setOffset(0, 18 if hovered else 12)
		self._shadow.setColor(QColor(0, 0, 0, 210 if hovered else 155))

		self.setStyleSheet(
			f"""
			QFrame#HomeRecCard {{
				background: rgba(8, 12, 20, 246);
				border: 1px solid {border};
				border-radius: 22px;
			}}

			QFrame#HomeRecCoverFrame {{
				background: rgba(0, 0, 0, 255);
				border: none;
				border-top-left-radius: 22px;
				border-top-right-radius: 22px;
			}}

			QLabel#HomeRecCoverImage {{
				background: transparent;
				border: none;
				border-top-left-radius: 22px;
				border-top-right-radius: 22px;
			}}

			QFrame#HomeRecCoverGlow {{
				background: {state_glow};
				border: none;
				border-top-left-radius: 22px;
				border-top-right-radius: 22px;
			}}

			QLabel#HomeRecTopBadge[role="difficulty"] {{
				background: {badge_bg};
				color: rgb(248, 249, 252);
				border: 1px solid {badge_border};
				border-radius: 12px;
				padding: 4px 10px;
				font-size: 11px;
				font-weight: 700;
			}}

			QLabel#HomeRecTopBadge[role="xp"] {{
				background: rgba(14, 18, 28, 196);
				color: rgb(245, 247, 255);
				border: 1px solid rgba(255, 255, 255, 34);
				border-radius: 12px;
				padding: 4px 10px;
				font-size: 11px;
				font-weight: 700;
			}}

			QLabel#HomeRecTitle {{
				background: transparent;
				border: none;
				color: rgb(246, 248, 252);
				font-size: 18px;
				font-weight: 700;
			}}

			QLabel#HomeRecMeta {{
				background: transparent;
				border: none;
				color: rgba(205, 212, 225, 182);
				font-size: 13px;
				font-weight: 500;
			}}

			QLabel#HomeRecReason {{
				background: transparent;
				border: none;
				color: rgba(223, 227, 236, 202);
				font-size: 14px;
				font-weight: 500;
			}}

			QLabel#HomeRecState {{
				background: rgba(255, 255, 255, 8);
				color: rgba(241, 244, 251, 210);
				border: 1px solid rgba(255, 255, 255, 18);
				border-radius: 11px;
				padding: 3px 10px;
				font-size: 11px;
				font-weight: 700;
			}}

			QPushButton#HomeRecCTA {{
				background: qlineargradient(
					x1:0, y1:0, x2:1, y2:0,
					stop:0 {button_top},
					stop:1 {button_bottom}
				);
				color: rgb(247, 249, 252);
				border: 1px solid {_rgba(accent, 118 if hovered else 84)};
				border-radius: 14px;
				padding: 0 14px;
				font-size: 14px;
				font-weight: 700;
				text-align: center;
			}}

			QPushButton#HomeRecCTA:hover {{
				border: 1px solid {_rgba(accent, 170)};
				background: qlineargradient(
					x1:0, y1:0, x2:1, y2:0,
					stop:0 {_rgba(accent, 84)},
					stop:1 {_rgba(accent, 42)}
				);
			}}
			"""
		)

	def _animate_hover(self, hovered: bool) -> None:
		self.setProperty("hovered", hovered)
		self._apply_visual_state()

		if self._base_rect.isNull():
			return

		target = QRect(self._base_rect)
		if hovered:
			target.translate(0, -self._lift_px)

		self._anim.stop()
		self._anim.setStartValue(self.geometry())
		self._anim.setEndValue(target)
		self._anim.start()

	def enterEvent(self, event):
		self._animate_hover(True)
		super().enterEvent(event)

	def leaveEvent(self, event):
		self._animate_hover(False)
		super().leaveEvent(event)


class _HoverCardHost(QFrame):
	def __init__(self, width: int = 356, height: int = 378, lift_px: int = 6, parent=None):
		super().__init__(parent)
		self._lift_px = lift_px
		self._card_w = width
		self._card_h = height - lift_px

		self.setAttribute(Qt.WA_StyledBackground, False)
		self.setFixedSize(width, height)

		self.card = _HoverCard(self)
		self.card.setObjectName("HomeRecCard")
		self.card.setAttribute(Qt.WA_StyledBackground, True)
		self.card.setFixedSize(self._card_w, self._card_h)
		self.card.set_base_geometry(QRect(0, self._lift_px, self._card_w, self._card_h))

class _AspectCoverLabel(QLabel):
	def __init__(self, parent=None):
		super().__init__(parent)
		self._pm = QPixmap()
		self.setAttribute(Qt.WA_StyledBackground, False)

	def set_cover_pixmap(self, pm: QPixmap) -> None:
		self._pm = pm if isinstance(pm, QPixmap) else QPixmap()
		self.update()

	def paintEvent(self, event):
		p = QPainter(self)
		p.setRenderHint(QPainter.SmoothPixmapTransform, True)

		if self._pm.isNull():
			p.end()
			return

		scaled = self._pm.scaled(
			self.size(),
			Qt.KeepAspectRatio,
			Qt.SmoothTransformation,
		)

		x = int((self.width() - scaled.width()) / 2)
		y = int((self.height() - scaled.height()) / 2)
		p.drawPixmap(x, y, scaled)
		p.end()

class HomeView(QWidget):
	nav_labs = pyqtSignal()
	request_select_lab = pyqtSignal(str)

	def __init__(self, state):
		super().__init__()
		self.state = state
		self._rec_scroller = None
		self._rec_scroll_anim = None
		self._hero_lab_id = ""

		self._rec_card_width = 356
		self._rec_card_height = 400
		self._rec_card_lift = 6
		self._rec_layout_top = 4
		self._rec_layout_bottom = 8

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(0)

		self.page_scroll = QScrollArea(self)
		self.page_scroll.setObjectName("HomePageScroll")
		self.page_scroll.setWidgetResizable(True)
		self.page_scroll.setFrameShape(QFrame.NoFrame)
		self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
		self.page_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.page_scroll.setStyleSheet(
			"QScrollArea#HomePageScroll { background: transparent; border: none; }"
		)
		self.page_scroll.viewport().setAutoFillBackground(False)
		self.page_scroll.viewport().setAttribute(Qt.WA_StyledBackground, False)
		outer.addWidget(self.page_scroll, 1)

		scroll_host = QWidget()
		scroll_host.setObjectName("HomeScrollHost")
		scroll_host.setAttribute(Qt.WA_StyledBackground, False)
		scroll_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
		self.page_scroll.setWidget(scroll_host)

		scroll_root = QVBoxLayout(scroll_host)
		scroll_root.setContentsMargins(0, 0, 0, 0)
		scroll_root.setSpacing(0)

		surface = QFrame()
		surface.setObjectName("ContentSurface")
		surface.setAttribute(Qt.WA_StyledBackground, True)
		surface.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
		scroll_root.addWidget(surface, 0, Qt.AlignTop)

		root = QVBoxLayout(surface)
		root.setContentsMargins(16, 12, 16, 12)
		root.setSpacing(16)

		# ---- Hero ----
		self.hero = QFrame()
		self.hero.setObjectName("HomeHero")
		self.hero.setAttribute(Qt.WA_StyledBackground, True)
		self.hero.setFixedHeight(380)
		self.hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		root.addWidget(self.hero)
		root.addSpacing(4)

		hero_layout = QHBoxLayout(self.hero)
		hero_layout.setContentsMargins(18, 16, 18, 16)
		hero_layout.setSpacing(18)

		hero_left = QVBoxLayout()
		hero_left.setSpacing(8)
		hero_left.setContentsMargins(0, 0, 0, 0)
		hero_layout.addLayout(hero_left, 3)

		self.hero_mode = QLabel("RECOMMENDED NEXT")
		self.hero_mode.setObjectName("HomeEyebrow")
		hero_left.addWidget(self.hero_mode)

		self.hero_title = QLabel("No labs discovered")
		self.hero_title.setObjectName("HomeHeroTitle")
		self.hero_title.setWordWrap(True)
		hero_left.addWidget(self.hero_title)

		self.hero_summary = QLabel("Install labs to turn Home into a mission hub.")
		self.hero_summary.setObjectName("HomeHeroSummary")
		self.hero_summary.setWordWrap(True)
		self.hero_summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		self.hero_summary.setFixedHeight(42)
		hero_left.addWidget(self.hero_summary)

		self.hero_meta_row = QHBoxLayout()
		self.hero_meta_row.setSpacing(6)
		hero_left.addLayout(self.hero_meta_row)

		self.hero_pill_diff = self._meta_pill("Difficulty")
		self.hero_pill_eta = self._meta_pill("ETA")
		self.hero_pill_focus = self._meta_pill("Web")
		self.hero_pill_xp = self._meta_pill("0 XP")
		for pill in (self.hero_pill_diff, self.hero_pill_eta, self.hero_pill_focus, self.hero_pill_xp):
			self.hero_meta_row.addWidget(pill, 0, Qt.AlignLeft)
		self.hero_meta_row.addStretch(1)

		self.hero_reward = QLabel("+0 XP • Ready for your next solve")
		self.hero_reward.setObjectName("HomeReward")
		hero_left.addWidget(self.hero_reward)

		self.hero_callout = QFrame()
		self.hero_callout.setObjectName("HomeCallout")
		self.hero_callout.setAttribute(Qt.WA_StyledBackground, True)
		self.hero_callout.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		self.hero_callout.setFixedHeight(56)
		hero_left.addWidget(self.hero_callout)

		callout_layout = QVBoxLayout(self.hero_callout)
		callout_layout.setContentsMargins(14, 8, 14, 8)
		callout_layout.setSpacing(2)

		self.hero_callout_title = QLabel("Mission Snapshot")
		self.hero_callout_title.setObjectName("HomeCalloutTitle")
		self.hero_callout_title.setWordWrap(False)
		callout_layout.addWidget(self.hero_callout_title)

		self.hero_callout_meta = QLabel("Resume where you left off.")
		self.hero_callout_meta.setObjectName("HomeCalloutMeta")
		self.hero_callout_meta.setWordWrap(False)
		callout_layout.addWidget(self.hero_callout_meta)

		hero_cta_row = QHBoxLayout()
		hero_cta_row.setSpacing(12)
		hero_left.addLayout(hero_cta_row)

		self.hero_primary = QPushButton("Open Mission")
		self.hero_primary.setObjectName("PrimaryButton")
		self.hero_primary.setCursor(Qt.PointingHandCursor)
		self.hero_primary.clicked.connect(self._open_hero_lab)
		self.hero_primary.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
		self.hero_primary.setMinimumWidth(132)
		hero_cta_row.addWidget(self.hero_primary, 0, Qt.AlignLeft)

		self.hero_secondary = QPushButton("Browse Labs")
		self.hero_secondary.setObjectName("GhostButton")
		self.hero_secondary.setCursor(Qt.PointingHandCursor)
		self.hero_secondary.clicked.connect(self.nav_labs.emit)
		self.hero_secondary.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
		self.hero_secondary.setMinimumWidth(132)
		hero_cta_row.addWidget(self.hero_secondary, 0, Qt.AlignLeft)
		hero_cta_row.addStretch(1)

		hero_right = QVBoxLayout()
		hero_right.setSpacing(0)
		hero_right.setContentsMargins(0, 0, 0, 0)
		hero_right.setAlignment(Qt.AlignTop)
		hero_layout.addLayout(hero_right, 2)

		badge_row = QHBoxLayout()
		badge_row.setContentsMargins(0, 0, 0, 0)
		badge_row.setSpacing(0)
		badge_row.addStretch(1)

		self.hero_badge = QLabel("RECOMMENDED")
		self.hero_badge.setObjectName("HomeStateBadge")
		badge_row.addWidget(self.hero_badge, 0, Qt.AlignRight | Qt.AlignTop)
		hero_right.addLayout(badge_row)

		self.hero_art = QLabel()
		self.hero_art_size = 320
		self.hero_art.setObjectName("HomeHeroArt")
		self.hero_art.setParent(self.hero)
		self.hero_art.setFixedSize(self.hero_art_size, self.hero_art_size)
		self.hero_art.setAlignment(Qt.AlignCenter)

		self._hero_art_offset_y = -20  # ← tweak this value to move up/down
		self._hero_art_offset_x = -200  # tweak to move left/right (negative = left)

		# ---- Recommended labs intro/header ----
		self.rec_intro = QFrame()
		self.rec_intro.setObjectName("HomeRecIntro")
		self.rec_intro.setAttribute(Qt.WA_StyledBackground, True)
		self.rec_intro.setStyleSheet(
			"""
			QFrame#HomeRecIntro {
				background: transparent;
				border: none;
			}
			QFrame#HomeRecRule {
				background: rgba(245, 197, 66, 34);
				border: none;
			}
			QLabel#HomeRecEyebrow {
				color: rgba(245, 197, 66, 230);
				font-size: 12px;
				font-weight: 700;
			}
			QLabel#HomeRecHeaderTitle {
				color: rgb(245, 247, 252);
				font-size: 22px;
				font-weight: 800;
			}
			QLabel#HomeRecHeaderMeta {
				color: rgba(194, 202, 218, 185);
				font-size: 13px;
				font-weight: 500;
			}
			QLabel#HomeRecCountChip {
				background: rgba(18, 22, 34, 210);
				color: rgb(245, 247, 252);
				border: 1px solid rgba(255, 255, 255, 30);
				border-radius: 16px;
				padding: 8px 16px;
				font-size: 12px;
				font-weight: 700;
			}
			"""
		)
		root.addWidget(self.rec_intro)

		rec_intro_layout = QVBoxLayout(self.rec_intro)
		rec_intro_layout.setContentsMargins(2, 6, 2, 8)
		rec_intro_layout.setSpacing(10)

		self.rec_intro_rule = QFrame()
		self.rec_intro_rule.setObjectName("HomeRecRule")
		self.rec_intro_rule.setAttribute(Qt.WA_StyledBackground, True)
		self.rec_intro_rule.setFixedHeight(1)
		rec_intro_layout.addWidget(self.rec_intro_rule)

		# keep the gold divider line, but remove the extra eyebrow row
		rec_header = QHBoxLayout()
		rec_header.setContentsMargins(0, 0, 0, 0)
		rec_header.setSpacing(16)
		rec_intro_layout.addLayout(rec_header)

		rec_header_left = QVBoxLayout()
		rec_header_left.setContentsMargins(0, 0, 0, 0)
		rec_header_left.setSpacing(2)
		rec_header.addLayout(rec_header_left, 1)

		self.rec_title = QLabel("Recommended Next Labs")
		self.rec_title.setObjectName("HomeRecHeaderTitle")
		rec_header_left.addWidget(self.rec_title)

		self.rec_subtitle = QLabel("Targets selected from your progression, recent solves, and XP path.")
		self.rec_subtitle.setObjectName("HomeRecHeaderMeta")
		self.rec_subtitle.setWordWrap(True)
		rec_header_left.addWidget(self.rec_subtitle)

		rec_header.addStretch(1)

		self.rec_stage = QFrame()
		self.rec_stage.setObjectName("HomeRecStage")
		self.rec_stage.setAttribute(Qt.WA_StyledBackground, True)
		self.rec_stage.setStyleSheet("QFrame#HomeRecStage { background: transparent; border: none; }")
		self.rec_stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		self.rec_stage.setFixedHeight(self._rec_layout_top + self._rec_card_height + self._rec_layout_bottom)
		root.addWidget(self.rec_stage, 0)

		rec_stage_layout = QHBoxLayout(self.rec_stage)
		rec_stage_layout.setContentsMargins(0, 0, 0, 0)
		rec_stage_layout.setSpacing(0)

		self.rec_scroll = QScrollArea(self.rec_stage)
		self.rec_scroll.setObjectName("HomeRecScroll")
		self.rec_scroll.setWidgetResizable(False)
		self.rec_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.rec_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
		self.rec_scroll.setFrameShape(QFrame.NoFrame)
		self.rec_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.rec_scroll.setStyleSheet("QScrollArea#HomeRecScroll { background: transparent; border: none; }")
		self.rec_scroll.viewport().setAutoFillBackground(False)
		self.rec_scroll.viewport().setAttribute(Qt.WA_StyledBackground, False)
		rec_stage_layout.addWidget(self.rec_scroll, 1)

		self.rec_left_btn = QPushButton("←", self.rec_stage)
		self.rec_left_btn.setObjectName("HomeCarouselArrow")
		self.rec_left_btn.setCursor(Qt.PointingHandCursor)
		self.rec_left_btn.setFixedSize(40, 40)
		self.rec_left_btn.clicked.connect(lambda: self._scroll_recommendations(-1))
		self.rec_left_btn.hide()

		arrow_css = (
			"QPushButton#HomeCarouselArrow {"
			" background: transparent;"
			" border: none;"
			" color: rgb(245, 197, 66);"
			" font-size: 24px;"
			" font-weight: 700;"
			" padding: 0px;"
			"}"
			"QPushButton#HomeCarouselArrow:hover { color: rgb(255, 216, 106); }"
			"QPushButton#HomeCarouselArrow:disabled { color: rgba(245, 197, 66, 70); }"
		)
		self.rec_left_btn.setStyleSheet(arrow_css)
		self.rec_left_btn.raise_()

		self.rec_right_btn = QPushButton("→", self.rec_stage)
		self.rec_right_btn.setObjectName("HomeCarouselArrow")
		self.rec_right_btn.setCursor(Qt.PointingHandCursor)
		self.rec_right_btn.setFixedSize(40, 40)
		self.rec_right_btn.clicked.connect(lambda: self._scroll_recommendations(1))
		self.rec_right_btn.hide()
		self.rec_right_btn.setStyleSheet(arrow_css)
		self.rec_right_btn.raise_()

		self.rec_scroll_host = QWidget()
		self.rec_scroll_host.setObjectName("HomeRecScrollHost")
		self.rec_scroll_host.setAttribute(Qt.WA_StyledBackground, False)
		self.rec_scroll_host.setStyleSheet("background: transparent;")
		self.rec_scroll.setWidget(self.rec_scroll_host)

		self._setup_recommendation_drag_scroll()

		self.rec_cards_layout = QHBoxLayout(self.rec_scroll_host)
		self.rec_cards_layout.setContentsMargins(
			self._rec_layout_top,
			self._rec_layout_top,
			self._rec_layout_top,
			self._rec_layout_bottom,
		)
		self.rec_cards_layout.setSpacing(8)

		self.rec_cards = []
		for _idx in range(9):
			card, refs = self._build_recommendation_card()
			self.rec_cards_layout.addWidget(card)
			self.rec_cards.append((card, refs))

		try:
			self.rec_scroll.horizontalScrollBar().valueChanged.connect(self._refresh_rec_nav)
			self.rec_scroll.horizontalScrollBar().rangeChanged.connect(lambda _min, _max: self._refresh_rec_nav())
		except Exception:
			pass

		try:
			self.rec_stage.installEventFilter(self)
			self.rec_scroll.viewport().installEventFilter(self)
			self.rec_left_btn.installEventFilter(self)
			self.rec_right_btn.installEventFilter(self)
		except Exception:
			pass

		self._refresh_all()
		QTimer.singleShot(0, self._position_hero_art)

		try:
			self.state.labs_changed.connect(self._refresh_all)
		except Exception:
			pass
		try:
			if hasattr(self.state, "progress_changed"):
				self.state.progress_changed.connect(self._refresh_all)
		except Exception:
			pass
		try:
			if hasattr(self.state, "player_stats_changed"):
				self.state.player_stats_changed.connect(self._refresh_all)
		except Exception:
			pass
		try:
			self.state.running_changed.connect(lambda _lab: self._refresh_all())
		except Exception:
			pass

	def eventFilter(self, obj, event):
		try:
			if obj in (self.rec_stage, self.rec_scroll.viewport(), self.rec_left_btn, self.rec_right_btn):
				if event.type() == QEvent.Enter:
					self._set_rec_arrows_visible(True)
					if obj == self.rec_scroll.viewport():
						try:
							if self._rec_scroller is None or self._rec_scroller.state() != QScroller.Dragging:
								self.rec_scroll.viewport().setCursor(Qt.OpenHandCursor)
						except Exception:
							pass
				elif event.type() == QEvent.Leave:
					QTimer.singleShot(0, self._maybe_hide_rec_arrows)
					if obj == self.rec_scroll.viewport():
						try:
							if self._rec_scroller is None or self._rec_scroller.state() != QScroller.Dragging:
								self.rec_scroll.viewport().unsetCursor()
						except Exception:
							pass
		except Exception:
			pass
		return super().eventFilter(obj, event)

	def _position_hero_art(self) -> None:
		if not hasattr(self, "hero_art") or not hasattr(self, "hero"):
			return
		hero_w = self.hero.width()
		hero_h = self.hero.height()
		art_s = self.hero_art_size
		x = hero_w - art_s - 24 + self._hero_art_offset_x
		y = (hero_h - art_s) // 2 + self._hero_art_offset_y
		self.hero_art.move(x, y)
		self.hero_art.raise_()

	def resizeEvent(self, event):
		super().resizeEvent(event)
		self._position_rec_arrows()
		self._position_hero_art()

	def _setup_recommendation_drag_scroll(self) -> None:
		try:
			viewport = self.rec_scroll.viewport()
			viewport.setAttribute(Qt.WA_AcceptTouchEvents, True)
			viewport.setCursor(Qt.OpenHandCursor)

			self._rec_scroller = QScroller.scroller(viewport)

			props = self._rec_scroller.scrollerProperties()
			props.setScrollMetric(
				QScrollerProperties.FrameRate,
				QScrollerProperties.Fps60,
			)
			props.setScrollMetric(
				QScrollerProperties.ScrollingCurve,
				QEasingCurve(QEasingCurve.OutCubic),
			)

			props.setScrollMetric(
				QScrollerProperties.HorizontalOvershootPolicy,
				QScrollerProperties.OvershootAlwaysOff,
			)
			props.setScrollMetric(
				QScrollerProperties.VerticalOvershootPolicy,
				QScrollerProperties.OvershootAlwaysOff,
			)
			props.setScrollMetric(QScrollerProperties.AxisLockThreshold, 1.0)
			props.setScrollMetric(QScrollerProperties.MousePressEventDelay, 0.04)
			props.setScrollMetric(QScrollerProperties.DragStartDistance, 0.0025)
			props.setScrollMetric(QScrollerProperties.DragVelocitySmoothingFactor, 0.18)
			props.setScrollMetric(QScrollerProperties.DecelerationFactor, 0.12)
			self._rec_scroller.setScrollerProperties(props)

			try:
				self._rec_scroller.stateChanged.connect(self._on_rec_scroller_state_changed)
			except Exception:
				pass

			QScroller.grabGesture(viewport, QScroller.LeftMouseButtonGesture)
		except Exception:
			self._rec_scroller = None

	def _on_rec_scroller_state_changed(self, state) -> None:
		try:
			viewport = self.rec_scroll.viewport()
			if state == QScroller.Dragging:
				try:
					if self._rec_scroll_anim is not None:
						self._rec_scroll_anim.stop()
				except Exception:
					pass
				viewport.setCursor(Qt.ClosedHandCursor)
			elif viewport.underMouse():
				viewport.setCursor(Qt.OpenHandCursor)
			else:
				viewport.unsetCursor()
		except Exception:
			pass

	def _animate_rec_scroll_to(self, target_value: int, duration: int = 420) -> None:
		try:
			bar = self.rec_scroll.horizontalScrollBar()
			start_value = int(bar.value())
			end_value = max(0, min(int(target_value), int(bar.maximum())))

			if start_value == end_value:
				return

			try:
				if self._rec_scroll_anim is not None:
					self._rec_scroll_anim.stop()
			except Exception:
				pass

			self._rec_scroll_anim = QPropertyAnimation(bar, b"value", self)
			self._rec_scroll_anim.setDuration(int(duration))
			self._rec_scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
			self._rec_scroll_anim.setStartValue(start_value)
			self._rec_scroll_anim.setEndValue(end_value)

			def _clear_anim():
				self._rec_scroll_anim = None

			self._rec_scroll_anim.finished.connect(_clear_anim)
			self._rec_scroll_anim.start()
		except Exception:
			try:
				self.rec_scroll.horizontalScrollBar().setValue(int(target_value))
			except Exception:
				pass

	def _position_rec_arrows(self) -> None:
		try:
			if not hasattr(self, "rec_stage") or not hasattr(self, "rec_scroll"):
				return

			stage_h = self.rec_stage.height()
			left_x = 8
			right_x = max(8, self.rec_stage.width() - self.rec_right_btn.width() - 8)
			y = max(0, int((stage_h - self.rec_left_btn.height()) / 2))

			self.rec_left_btn.move(left_x, y)
			self.rec_right_btn.move(right_x, y)
			self.rec_left_btn.raise_()
			self.rec_right_btn.raise_()
		except Exception:
			pass

	def _set_rec_arrows_visible(self, visible: bool) -> None:
		try:
			bar = self.rec_scroll.horizontalScrollBar()
			maximum = int(bar.maximum())
			value = int(bar.value())

			can_go_left = value > 0
			can_go_right = value < maximum
			show_any = bool(visible and maximum > 0)

			self.rec_left_btn.setVisible(show_any and can_go_left)
			self.rec_right_btn.setVisible(show_any and can_go_right)

			self.rec_left_btn.setEnabled(can_go_left)
			self.rec_right_btn.setEnabled(can_go_right)
		except Exception:
			pass

	def _maybe_hide_rec_arrows(self) -> None:
		try:
			if (
				self.rec_stage.underMouse()
				or self.rec_scroll.viewport().underMouse()
				or self.rec_left_btn.underMouse()
				or self.rec_right_btn.underMouse()
			):
				self._set_rec_arrows_visible(True)
			else:
				self._set_rec_arrows_visible(False)
		except Exception:
			pass

	def _scroll_recommendations(self, direction: int) -> None:
		try:
			bar = self.rec_scroll.horizontalScrollBar()
			step = max(320, int(self.rec_scroll.viewport().width() * 0.82))
			self._animate_rec_scroll_to(bar.value() + (direction * step))
		except Exception:
			pass

	def _refresh_rec_nav(self) -> None:
		try:
			hovering = (
				self.rec_stage.underMouse()
				or self.rec_scroll.viewport().underMouse()
				or self.rec_left_btn.underMouse()
				or self.rec_right_btn.underMouse()
			)
			self._set_rec_arrows_visible(hovering)
		except Exception:
			pass

	def _meta_pill(self, text: str) -> QLabel:
		lbl = QLabel(text)
		lbl.setObjectName("HomeMetaPill")
		lbl.setAlignment(Qt.AlignCenter)
		return lbl

	def _set_meta_pill(self, lbl: QLabel, text: str, variant: str = "neutral") -> None:
		lbl.setText(text)
		lbl.setProperty("variant", variant)
		self._refresh_style(lbl)

	def _refresh_style(self, widget) -> None:
		try:
			widget.style().unpolish(widget)
			widget.style().polish(widget)
			widget.update()
		except Exception:
			pass

	def _lab_cover_pixmap(self, lab, width: int, height: int) -> QPixmap:
		try:
			imgp = getattr(lab, "image_path", None)
			img = imgp() if callable(imgp) else None
			if img:
				pm = QPixmap(str(img))
				if not pm.isNull():
					return pm
		except Exception:
			pass

		try:
			return self._lab_icon_pixmap(lab, max(width, height))
		except Exception:
			pm = QPixmap(width, height)
			pm.fill(Qt.transparent)
			return pm

	def _recommendation_tag(self, lab, lab_is_solved: bool, total_xp: int, solved_count: int, completion: int) -> Tuple[str, str]:
		if lab_is_solved:
			return "Replay Target", "solved"

		target_rank = self._recommended_target_difficulty(total_xp, solved_count, completion)
		lab_rank = self._difficulty_rank(lab)

		if lab_rank > target_rank:
			return "Stretch Target", "stretch"

		return "Recommended", "recommended"


	def _set_rec_state_chip(self, label: QLabel, role: str, difficulty_key: str) -> None:
		accent = _accent_for_difficulty(difficulty_key)

		if role == "solved":
			bg = "rgba(42, 196, 121, 26)"
			border = "rgba(42, 196, 121, 110)"
			text = "rgb(101, 232, 156)"
		elif role == "stretch":
			bg = _rgba(accent, 26)
			border = _rgba(accent, 120)
			text = "rgb(247, 249, 252)"
		else:
			bg = "rgba(255, 255, 255, 10)"
			border = "rgba(255, 255, 255, 22)"
			text = "rgba(245, 247, 252, 215)"

		label.setStyleSheet(
			f"""
			QLabel#HomeRecState {{
				background: {bg};
				color: {text};
				border: 1px solid {border};
				border-radius: 11px;
				padding: 3px 10px;
				font-size: 11px;
				font-weight: 700;
			}}
			"""
		)

	def _build_recommendation_card(self):
		host = _HoverCardHost(
			width=self._rec_card_width,
			height=self._rec_card_height,
			lift_px=self._rec_card_lift,
		)
		card = host.card

		root = QVBoxLayout(card)
		root.setContentsMargins(0, 0, 0, 0)
		root.setSpacing(0)

		cover_frame = QFrame()
		cover_frame.setObjectName("HomeRecCoverFrame")
		cover_frame.setAttribute(Qt.WA_StyledBackground, True)
		cover_frame.setFixedHeight(150)

		cover_grid = QGridLayout(cover_frame)
		cover_grid.setContentsMargins(0, 0, 0, 0)
		cover_grid.setSpacing(0)

		cover = _AspectCoverLabel()
		cover.setObjectName("HomeRecCoverImage")
		cover.setAlignment(Qt.AlignCenter)

		cover_grid.addWidget(cover, 0, 0)

		cover_glow = QFrame()
		cover_glow.setObjectName("HomeRecCoverGlow")
		cover_glow.setAttribute(Qt.WA_StyledBackground, True)
		cover_glow.setStyleSheet("background: transparent; border: none;")
		cover_glow.setAttribute(Qt.WA_TransparentForMouseEvents, True)
		cover_grid.addWidget(cover_glow, 0, 0)

		overlay = QFrame()
		overlay.setAttribute(Qt.WA_StyledBackground, False)
		overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)

		overlay_layout = QHBoxLayout(overlay)
		overlay_layout.setContentsMargins(12, 12, 12, 0)
		overlay_layout.setSpacing(8)

		diff_badge = QLabel("MEDIUM")
		diff_badge.setObjectName("HomeRecTopBadge")
		diff_badge.setProperty("role", "difficulty")
		diff_badge.setAlignment(Qt.AlignCenter)
		overlay_layout.addWidget(diff_badge, 0, Qt.AlignLeft)

		overlay_layout.addStretch(1)

		xp_badge = QLabel("120 XP")
		xp_badge.setObjectName("HomeRecTopBadge")
		xp_badge.setProperty("role", "xp")
		xp_badge.setAlignment(Qt.AlignCenter)
		overlay_layout.addWidget(xp_badge, 0, Qt.AlignRight)

		cover_grid.addWidget(overlay, 0, 0, Qt.AlignTop)
		root.addWidget(cover_frame)

		body = QFrame()
		body.setAttribute(Qt.WA_StyledBackground, False)
		body_layout = QVBoxLayout(body)
		body_layout.setContentsMargins(18, 16, 18, 18)
		body_layout.setSpacing(10)

		title = QLabel("—")
		title.setObjectName("HomeRecTitle")
		title.setWordWrap(True)
		body_layout.addWidget(title)

		meta = QLabel("45–75 min • API")
		meta.setObjectName("HomeRecMeta")
		meta.setWordWrap(False)
		body_layout.addWidget(meta)

		reason = QLabel("Recommended because it fits your current progression.")
		reason.setObjectName("HomeRecReason")
		reason.setWordWrap(True)
		reason.setFixedHeight(44)
		body_layout.addWidget(reason)

		body_layout.addStretch(1)

		state = QLabel("Recommended")
		state.setObjectName("HomeRecState")
		state.setAlignment(Qt.AlignCenter)
		body_layout.addWidget(state, 0, Qt.AlignLeft)

		action = QPushButton("Open Lab")
		action.setObjectName("HomeRecCTA")
		action.setCursor(Qt.PointingHandCursor)
		action.setFixedHeight(44)
		action.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
		action.clicked.connect(lambda: self._open_lab_from_button(action))
		body_layout.addWidget(action)

		root.addWidget(body, 1)

		refs = {
			"host": host,
			"shell": card,
			"cover": cover,
			"cover_glow": cover_glow,
			"diff_badge": diff_badge,
			"xp_badge": xp_badge,
			"title": title,
			"meta": meta,
			"reason": reason,
			"state": state,
			"button": action,
		}
		return host, refs

	def _open_hero_lab(self):
		if self._hero_lab_id:
			self.request_select_lab.emit(self._hero_lab_id)

	def _open_lab_from_button(self, button: QPushButton):
		lab_id = str(button.property("lab_id") or "")
		if lab_id:
			self.request_select_lab.emit(lab_id)

	def _running_lab(self):
		try:
			if hasattr(self.state, "running") and callable(getattr(self.state, "running")):
				return self.state.running()
		except Exception:
			pass
		try:
			running_id = get_running_lab()
			if not running_id:
				return None
			return next((lab for lab in self.state.labs() if str(getattr(lab, "id", "")) == str(running_id)), None)
		except Exception:
			return None

	def _progress_map(self) -> dict:
		try:
			if hasattr(self.state, "progress_map"):
				return self.state.progress_map() or {}
		except Exception:
			pass
		try:
			return progress_db.get_progress_map() or {}
		except Exception:
			return {}

	def _difficulty_key(self, lab) -> str:
		return str(getattr(lab, "difficulty", "") or "").strip().lower()

	def _difficulty_rank(self, lab) -> int:
		return _DIFF_ORDER.get(self._difficulty_key(lab), 99)

	def _eta_text(self, lab) -> str:
		diff = self._difficulty_key(lab)
		return {
			"easy": "30–45 min",
			"medium": "45–75 min",
			"hard": "75–120 min",
			"master": "2h+",
		}.get(diff, "45–60 min")

	def _focus_text(self, lab) -> str:
		hay = f"{getattr(lab, 'description', '')} {getattr(lab, 'story', '')}".lower()
		if any(k in hay for k in ("jwt", "token", "auth")):
			return "Auth"
		if any(k in hay for k in ("api", "graphql", "rest")):
			return "API"
		if any(k in hay for k in ("ssrf", "request", "internal")):
			return "Network"
		if any(k in hay for k in ("sqli", "sql", "database")):
			return "Data"
		return "Web"

	def _summary_text(self, lab) -> str:
		for value in (getattr(lab, "description", ""), getattr(lab, "story", "")):
			text = str(value or "").strip()
			if text:
				text = text.replace("\n", " ").strip()
				if len(text) > 125:
					text = text[:122].rstrip() + "…"
				return text
		return "A realistic web mission with a deeper business impact chain."

	def _lab_icon_pixmap(self, lab, size: int) -> QPixmap:
		try:
			imgp = getattr(lab, "image_path", None)
			img = imgp() if callable(imgp) else None
			if img:
				return lab_badge_icon(lab.name, getattr(lab, "difficulty", None), img, size).pixmap(size, size)
		except Exception:
			pass
		try:
			return lab_circle_icon(lab.name, getattr(lab, "difficulty", None), size).pixmap(size, size)
		except Exception:
			return _emblem((getattr(lab, "name", "?") or "?")[:1], size)

	def _recommended_target_difficulty(self, total_xp: int, solved_count: int, completion: int) -> int:
		operator_floor = next((int(th) for th, name in _RANK_TIERS if name == "Operator"), 500)
		specialist_floor = next((int(th) for th, name in _RANK_TIERS if name == "Specialist"), 1500)
		veteran_floor = next((int(th) for th, name in _RANK_TIERS if name == "Veteran"), 3500)

		if solved_count <= 1:
			return 0

		if completion < 15:
			return 0

		if total_xp < operator_floor:
			return 1 if completion >= 20 else 0

		if total_xp < specialist_floor:
			return 2 if completion >= 45 else 1

		if total_xp < veteran_floor:
			return 3 if completion >= 85 else 2

		return 3

	def _hero_lab(self, labs: List, progress: dict, total_xp: int, solved_count: int, completion: int):
		running = self._running_lab()
		if running is not None:
			return running, "active"

		started_unsolved = []
		for lab in labs:
			row = progress.get(str(getattr(lab, "id", "")), {}) or {}
			if row.get("started_at") and not row.get("solved_at"):
				started_unsolved.append((str(row.get("started_at") or ""), lab))
		if started_unsolved:
			started_unsolved.sort(key=lambda t: t[0], reverse=True)
			return started_unsolved[0][1], "continue"

		recs = self._recommended_labs(labs, progress, total_xp, solved_count, completion, exclude_ids=set(), limit=1)
		if recs:
			return recs[0], "recommended"

		return (labs[0], "recommended") if labs else (None, "recommended")

	def _recommended_labs(
		self,
		labs: List,
		progress: dict,
		total_xp: int,
		solved_count: int,
		completion: int,
		exclude_ids: set,
		limit: int = 9,
	) -> List:
		eligible = [
			lab for lab in labs
			if str(getattr(lab, "id", "")) not in exclude_ids
		]

		if not eligible:
			return []

		target = self._recommended_target_difficulty(total_xp, solved_count, completion)

		def _score(lab) -> Tuple[int, int, str]:
			rank = self._difficulty_rank(lab)
			return (abs(rank - target), rank, str(getattr(lab, "name", "")).lower())

		unsolved = [
			lab for lab in eligible
			if not self.state.is_solved(getattr(lab, "id", ""))
		]
		solved = [
			lab for lab in eligible
			if self.state.is_solved(getattr(lab, "id", ""))
		]

		unsolved.sort(key=_score)
		solved.sort(key=_score)

		recs = list(unsolved[:limit])

		if len(recs) < limit:
			remaining = limit - len(recs)
			recs.extend(solved[:remaining])

		return recs[:limit]

	def _recommendation_reason(self, lab, total_xp: int, solved_count: int, completion: int) -> str:
		diff = self._difficulty_key(lab)

		if diff == "easy":
			if solved_count <= 1:
				return "Fast solve to build momentum."
			return "Quick confidence win between deeper chains."

		if diff == "medium":
			return "Clean next step beyond Easy progression."

		if diff == "hard":
			if completion >= 50 or total_xp >= 1500:
				return "Deeper chain aligned to your progression."
			return "Stretch target with stronger business impact."

		if diff == "master":
			return "High-complexity target with premium XP payoff."

		return "Good fit for your current progression."

	def _latest_solved(self, labs: List, progress: dict):
		solved = []
		for lab in labs:
			row = progress.get(str(getattr(lab, "id", "")), {}) or {}
			if row.get("solved_at"):
				solved.append((str(row.get("solved_at") or ""), lab))
		if not solved:
			return None
		solved.sort(key=lambda t: t[0], reverse=True)
		return solved[0][1]

	def _next_rank_message(self, total_xp: int, next_name: Optional[str], next_floor: Optional[int]) -> Tuple[str, str]:
		if next_name and next_floor is not None:
			need = max(0, int(next_floor) - total_xp)
			if need <= 0:
				return "Rank threshold reached", f"You have enough XP for {next_name}. Refreshing your profile should catch up shortly."
			return "1 step from rank-up", f"Open this mission to move {need} XP closer to {next_name}."
		return "Max rank reached", "Use Home to revisit labs, maintain streaks, and keep the mission log active."

	def _refresh_activity_row(self, refs: Dict[str, QLabel], title: str, meta: str, badge_text: str, variant: str) -> None:
		refs["title"].setText(title)
		refs["meta"].setText(meta)
		refs["badge"].setText(badge_text)
		refs["badge"].setProperty("variant", variant)
		refs["dot"].setProperty("variant", variant)
		self._refresh_style(refs["badge"])
		self._refresh_style(refs["dot"])

	def _refresh_all(self):
		labs = self.state.labs()
		progress = self._progress_map()
		stats = progress_db.get_device_stats()

		total = len(labs)
		solved_count = _solved_count(labs, progress)
		completion = _completion_percent(total, solved_count)
		total_xp = int(getattr(stats, "xp", 0) or 0)
		next_name = getattr(stats, "next_rank", None)
		next_floor = getattr(stats, "next_rank_xp", None)
		streak = int(getattr(stats, "streak_days", 0) or 0)

		hero_lab, hero_mode = self._hero_lab(labs, progress, total_xp, solved_count, completion)
		self._hero_lab_id = str(getattr(hero_lab, "id", "") or "") if hero_lab else ""

		if hero_lab is None:
			self.hero_mode.setText("MISSION READY")
			self.hero_title.setText("No labs discovered")
			self.hero_summary.setText("Install labs to turn Home into a mission hub.")
			self.hero_summary.show()
			self.hero_callout_title.setText("Mission Snapshot")
			self.hero_callout_meta.setText("Install labs to unlock your first mission.")
			self._set_meta_pill(self.hero_pill_diff, "Catalog", "neutral")
			self._set_meta_pill(self.hero_pill_eta, "—", "neutral")
			self._set_meta_pill(self.hero_pill_focus, "WebVerse", "neutral")
			self._set_meta_pill(self.hero_pill_xp, "0 XP", "neutral")
			self.hero_reward.setText("Add labs to unlock recommendations, activity, and rank momentum.")
			self.hero_primary.setText("Open Browse Labs")
			self.hero_secondary.setText("Browse Labs")
			self.hero_badge.setText("READY")
			self.hero_badge.setProperty("variant", "neutral")
			self._refresh_style(self.hero_badge)
			self.hero_art.setPixmap(_emblem("W", self.hero_art_size))
			try:
				self.hero_primary.clicked.disconnect()
			except Exception:
				pass
			self.hero_primary.clicked.connect(self.nav_labs.emit)
		else:
			try:
				self.hero_primary.clicked.disconnect()
			except Exception:
				pass
			self.hero_primary.clicked.connect(self._open_hero_lab)

			mode_copy = {
				"active": "CONTINUE MISSION",
				"continue": "PICK UP WHERE YOU LEFT OFF",
				"recommended": "RECOMMENDED NEXT",
			}
			badge_copy = {
				"active": ("ACTIVE MISSION", "active"),
				"continue": ("IN PROGRESS", "warn"),
				"recommended": ("RECOMMENDED", "neutral"),
			}
			primary_copy = {
				"active": "Continue Lab",
				"continue": "Continue Lab",
				"recommended": "Open Mission",
			}
			reward_copy = {
				"active": f"+{base_xp_for_difficulty(getattr(hero_lab, 'difficulty', '') or '')} XP • Active mission",
				"continue": "Resume your in-progress target",
				"recommended": f"+{base_xp_for_difficulty(getattr(hero_lab, 'difficulty', '') or '')} XP • {self._recommendation_reason(hero_lab, total_xp, solved_count, completion)}",
			}

			self.hero_mode.setText(mode_copy.get(hero_mode, "RECOMMENDED NEXT"))
			self.hero_title.setText(str(getattr(hero_lab, "name", "Untitled Lab") or "Untitled Lab"))
			self.hero_summary.setText(self._summary_text(hero_lab))
			self.hero_summary.show()
			self._set_meta_pill(self.hero_pill_diff, str(getattr(hero_lab, "difficulty", "Unknown") or "Unknown").upper(), self._difficulty_key(hero_lab) or "neutral")
			self._set_meta_pill(self.hero_pill_eta, self._eta_text(hero_lab), "neutral")
			self._set_meta_pill(self.hero_pill_focus, self._focus_text(hero_lab), "neutral")
			self._set_meta_pill(self.hero_pill_xp, f"{base_xp_for_difficulty(getattr(hero_lab, 'difficulty', '') or '')} XP", "neutral")
			self.hero_reward.setText(reward_copy.get(hero_mode, ""))

			self.hero_callout_title.setText("Mission Snapshot")
			if hero_mode == "active":
				self.hero_callout_meta.setText("Runtime is live. Re-open the mission and continue testing.")
			elif hero_mode == "continue":
				self.hero_callout_meta.setText("Unsolved mission. Resume where you left off.")
			else:
				self.hero_callout_meta.setText("Best next target based on your current progression.")

			self.hero_primary.setText(primary_copy.get(hero_mode, "Open Mission"))
			self.hero_secondary.setText("Browse Labs")

			badge_text, badge_variant = badge_copy.get(hero_mode, ("RECOMMENDED", "neutral"))
			self.hero_badge.setText(badge_text)
			self.hero_badge.setProperty("variant", badge_variant)
			self._refresh_style(self.hero_badge)

			self.hero_art.setPixmap(self._lab_icon_pixmap(hero_lab, self.hero_art_size))

		exclude_ids = {self._hero_lab_id} if self._hero_lab_id else set()
		recs = self._recommended_labs(labs, progress, total_xp, solved_count, completion, exclude_ids=exclude_ids, limit=9)

		for idx, (card, refs) in enumerate(self.rec_cards):
			if idx >= len(recs):
				card.setVisible(False)
				continue

			card.setVisible(True)

			lab = recs[idx]
			lab_id = str(getattr(lab, "id", "") or "")
			lab_name = str(getattr(lab, "name", "Untitled Lab") or "Untitled Lab")
			diff_key = self._difficulty_key(lab)
			diff_text = str(getattr(lab, "difficulty", "Unknown") or "Unknown").upper()
			xp_value = base_xp_for_difficulty(getattr(lab, "difficulty", "") or "")
			lab_is_solved = self.state.is_solved(lab_id)

			refs["shell"].set_difficulty_key(diff_key)
			refs["cover"].set_cover_pixmap(self._lab_cover_pixmap(lab, 356, 150))
			refs["diff_badge"].setText(diff_text)
			refs["xp_badge"].setText(f"{xp_value} XP")
			refs["title"].setText(lab_name)
			refs["meta"].setText(f"{self._eta_text(lab)} • {self._focus_text(lab)}")

			if lab_is_solved:
				refs["reason"].setText("Previously solved. Revisit this lab to reinforce the exploit chain.")
				refs["button"].setText("Replay Lab")
			else:
				refs["reason"].setText(self._recommendation_reason(lab, total_xp, solved_count, completion))
				refs["button"].setText("Open Lab")

			tag_text, tag_role = self._recommendation_tag(lab, lab_is_solved, total_xp, solved_count, completion)
			refs["state"].setText(tag_text)
			self._set_rec_state_chip(refs["state"], tag_role, diff_key)

			refs["button"].setProperty("lab_id", lab_id)

		try:
			visible_cards = min(len(recs), len(self.rec_cards))
			card_width = self._rec_card_width
			card_spacing = self.rec_cards_layout.spacing()
			left_margin = self._rec_layout_top
			right_margin = self._rec_layout_top
			top_margin = self._rec_layout_top
			bottom_margin = self._rec_layout_bottom

			host_width = left_margin + right_margin

			if visible_cards > 0:
				host_width += (visible_cards * card_width) + ((visible_cards - 1) * card_spacing)
			else:
				host_width = max(self.rec_scroll.viewport().width(), 720)

			host_height = top_margin + self._rec_card_height + bottom_margin
			self.rec_scroll_host.setFixedSize(host_width, host_height)
		except Exception:
			pass

		self._position_rec_arrows()
		self._refresh_rec_nav()
