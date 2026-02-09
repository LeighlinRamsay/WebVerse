# gui/theme.py
from __future__ import annotations

import math
import os

# Theme: Onyx Amber
# NOTE: Qt Style Sheets don't support CSS variables. We generate a QSS string.

DEFAULT_UI_SCALE = 1.18


def _i(x: float) -> int:
	return int(round(x))


def _s(px: float, scale: float) -> int:
	return max(0, _i(px * scale))


def qss_onyx_amber(scale: float = DEFAULT_UI_SCALE) -> str:
	base_font = max(12, _i(13 * scale))
	h1 = _i(26 * scale)
	h2 = _i(16 * scale)
	small = max(11, _i(12 * scale))

	r_sm = _s(10, scale)
	r_md = _s(12, scale)
	r_lg = _s(14, scale)
	r_xl = _s(18, scale)
	r_md_in = max(0, r_md - _s(2, scale))

	p_6 = _s(6, scale)
	p_8 = _s(8, scale)
	p_10 = _s(10, scale)
	p_12 = _s(12, scale)
	cb_ind = max(14, _s(16, scale))
	cb_r = max(5, _s(6, scale))
	p_14 = _s(14, scale)
	p_16 = _s(16, scale)
	p_18 = _s(18, scale)

	kpi_num = _i(18 * scale)
	kpi_lbl = max(11, _i(12 * scale))

	return f"""
	QWidget {{
		background: #07090C;
		color: rgba(235,241,255,0.90);
		font-family: Inter, "Segoe UI", Arial;
		font-size: {base_font}px;
	}}

	/* =========================
	   Auth Dialog (clean + premium)
	   ========================= */
	QDialog#AuthDialog {{
		background: rgba(10,12,16,0.96);
	}}

	/* Kill the “every widget paints a black box” look INSIDE auth dialogs */
	QDialog#AuthDialog QWidget {{
		background: transparent;
	}}

	QLabel#AuthTitle {{
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#AuthSub {{
		color: rgba(235,241,255,0.62);
		font-weight: 850;
	}}

	QLabel#AuthFieldLabel {{
		color: rgba(235,241,255,0.60);
		font-weight: 950;
		font-size: {small}px;
		letter-spacing: 0.3px;
		padding-left: 2px;
	}}

	QFrame#AuthPanel {{
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 18px;
	}}
	QLineEdit#AuthInput {{
		background: rgba(7,9,12,0.55);
		border: 1px solid rgba(255,255,255,0.12);
		border-radius: 14px;
		padding: {p_10}px {p_12}px;
		font-weight: 900;
		color: rgba(245,247,255,0.92);
	}}
	QLineEdit#AuthInput:focus {{
		border: 1px solid rgba(245,197,66,0.62);
		background: rgba(7,9,12,0.72);
	}}
	QCheckBox#AuthCheck {{
		color: rgba(235,241,255,0.88);
		font-weight: 850;
		background: transparent;
		spacing: {p_12}px;
	}}
	QCheckBox#AuthCheck::indicator {{
		width: {cb_ind}px;
		height: {cb_ind}px;
		border-radius: {cb_r}px;
		border: 1px solid rgba(255,255,255,0.18);
		background: rgba(255,255,255,0.03);
	}}
	QCheckBox#AuthCheck::indicator:hover {{
		border: 1px solid rgba(255,255,255,0.28);
		background: rgba(255,255,255,0.05);
	}}
	QCheckBox#AuthCheck::indicator:checked {{
		border: 1px solid rgba(245,197,66,0.78);
		background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
			stop:0 rgba(245,197,66,0.52),
			stop:1 rgba(245,197,66,0.24)
		);
		image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-32.png);
	}}
	QCheckBox#AuthCheck::indicator:checked:hover {{
		border: 1px solid rgba(245,197,66,0.92);
		background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
			stop:0 rgba(245,197,66,0.60),
			stop:1 rgba(245,197,66,0.28)
		);
	}}
	QCheckBox#AuthCheck::indicator:disabled {{
		border: 1px solid rgba(255,255,255,0.10);
		background: rgba(255,255,255,0.02);
	}}
	QCheckBox#AuthCheck::indicator:checked:disabled {{
		border: 1px solid rgba(245,197,66,0.24);
		background: rgba(245,197,66,0.10);
		image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-32.png);
	}}

	/* =========================
	   Profile badge (sidebar)
	   ========================= */
	QWidget#ProfileBadge {{
		background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
			stop:0 rgba(245,197,66,0.20),
			stop:0.45 rgba(16,20,28,0.65),
			stop:1 rgba(16,20,28,0.55)
		);
		border: 1px solid rgba(245,197,66,0.30);
		border-radius: 14px;
	}}
	QFrame#ProfileBadge:hover {{
		border: 1px solid rgba(245,197,66,0.42);
	}}
	QLabel#ProfileTitle {{
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#ProfileMeta {{
		font-weight: 950;
		color: rgba(245,197,66,0.96);
	}}
	QLabel#ProfileHint {{
		color: rgba(235,241,255,0.62);
		font-weight: 850;
	}}

	QLabel {{
		background: transparent;
	}}

	QCheckBox {{
		background: transparent;
	}}
	QRadioButton {{
		background: transparent;
	}}

	QToolButton {{
		background: transparent;
	}}

	QLabel#H1 {{ font-size: {h1}px; font-weight: 900; color: rgba(245,247,255,0.94); }}
	QLabel#H2 {{ font-size: {h2}px; font-weight: 800; color: rgba(245,247,255,0.94); }}
	QLabel#Muted {{ color: rgba(235,241,255,0.65); }}
	QLabel#Subtle {{ color: rgba(235,241,255,0.45); }}

	QFrame#AppShell {{
		background: #07090C;
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	QFrame#ContentSurface {{
		background: rgba(10,12,16,0.86);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: {r_xl}px;
	}}

	/* ---- Topbar ---- */
	QFrame#TopBar {{
		background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
			stop:0 rgba(12,14,18,0.82),
			stop:1 rgba(8,10,13,0.62)
		);
		border: none;
		border-bottom: 1px solid rgba(255,255,255,0.06);
	}}

	QLabel#TopBrand {{
		font-size: 14px;
		font-weight: 950;
		letter-spacing: 0.4px;
		color: rgba(245,247,255,0.92);
		padding-left: 4px;
		padding-right: 6px;
	}}

	QToolButton#TopNavBtn {{
		min-width: 34px;
		max-width: 34px;
		min-height: 34px;
		max-height: 34px;
		border-radius: 12px;
		border: 1px solid rgba(255,255,255,0.06);
		background: rgba(255,255,255,0.035);
	}}

	QToolButton#TopNavBtn:hover {{
		border: 1px solid rgba(255,255,255,0.10);
		background: rgba(255,255,255,0.06);
	}}

	QToolButton#TopNavBtn:pressed {{
		background: rgba(255,255,255,0.075);
	}}

	QToolButton#TopNavBtn:disabled {{
		border: 1px solid rgba(255,255,255,0.03);
		background: rgba(255,255,255,0.02);
		color: rgba(235,241,255,0.22);
	}}

	QFrame#RunPill {{
		background: rgba(255,255,255,0.035);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: 14px;
	}}

	QFrame#RunPill:hover {{
		border: 1px solid rgba(255,255,255,0.12);
		background: rgba(255,255,255,0.05);
	}}

	QLabel#RunState {{
		padding: 2px 10px;
		border-radius: 10px;
		font-weight: 900;
		letter-spacing: 1.0px;
		font-size: 12px;
	}}

	QLabel#RunState[variant="running"] {{
		color: rgba(210,255,235,0.98);
		background: rgba(28, 210, 120, 0.18);
		border: 1px solid rgba(28, 210, 120, 0.22);
	}}

	QLabel#RunState[variant="starting"] {{
		color: rgba(210,255,235,0.98);
		background: rgba(28, 210, 120, 0.18);
		border: 1px solid rgba(28, 210, 120, 0.22);
	}}

	QLabel#RunState[variant="stopping"] {{
		color: rgba(255, 226, 226, 0.98);
		background: rgba(255, 92, 92, 0.14);
		border: 1px solid rgba(255, 92, 92, 0.20);
	}}

	QLabel#RunState[variant="resetting"] {{
		color: rgba(255, 244, 214, 0.98);
		background: rgba(245, 197, 66, 0.14);
		border: 1px solid rgba(245, 197, 66, 0.22);
	}}

	QLabel#RunState[variant="stopped"] {{
		color: rgba(235,241,255,0.58);
		background: rgba(255,255,255,0.04);
		border: 1px solid rgba(255,255,255,0.06);
	}}

	QLabel#RunHint {{
		color: rgba(235,241,255,0.66);
		font-weight: 700;
		padding-left: 6px;
		padding-right: 10px;
	}}

	QLineEdit#SearchBox {{
		background: rgba(255,255,255,0.035);
		border: 1px solid rgba(255,255,255,0.07);
		border-radius: 14px;
		padding: {p_10}px {p_12}px;
		selection-background-color: rgba(245,197,66,0.30);
	}}

	QLineEdit#SearchBox:hover {{
		border: 1px solid rgba(255,255,255,0.10);
		background: rgba(255,255,255,0.045);
	}}

	QLineEdit#SearchBox:focus {{
		border: 1px solid rgba(255,176,72,0.42);
		background: rgba(255,255,255,0.05);
	}}

	/* ---- Sidebar ---- */
	QFrame#Sidebar {{
		background: rgba(10,12,16,0.70);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: {r_xl}px;
	}}

	QPushButton#NavButton {{
		text-align: left;
		padding: {p_12}px {p_14}px;
		border-radius: {r_md}px;
		background: rgba(16,20,28,0.45);
		border: 1px solid rgba(255,255,255,0.06);
		font-weight: 800;
	}}
	QPushButton#NavButton:hover {{
		background: rgba(16,20,28,0.62);
		border: 1px solid rgba(255,255,255,0.10);
	}}
	QPushButton#NavButton[active="true"] {{
		background: rgba(245,197,66,0.16);
		border: 1px solid rgba(245,197,66,0.30);
		color: rgba(245,247,255,0.95);
	}}

	QFrame#AuthBadge {{
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_md}px;
	}}

	QPushButton#AuthBadgeBtn {{
		border-radius: {r_md}px;
		padding: {p_8}px {p_10}px;
		border: 1px solid rgba(255,255,255,0.10);
		background: rgba(255,255,255,0.035);
		font-weight: 900;
		color: rgba(235,241,255,0.86);
	}}
	QPushButton#AuthBadgeBtn:hover {{
		border: 1px solid rgba(255,255,255,0.16);
		background: rgba(255,255,255,0.06);
		color: rgba(245,247,255,0.92);
	}}
	QPushButton#AuthBadgeBtn:pressed {{
		background: rgba(255,255,255,0.075);
	}}
	QPushButton#AuthBadgeBtn:disabled {{
		border: 1px solid rgba(255,255,255,0.06);
		background: rgba(255,255,255,0.02);
		color: rgba(235,241,255,0.22);
	}}

	/* ---- Cards / Tiles ---- */
	QFrame#Card {{
		background: rgba(16,20,28,0.45);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	/* ---- Flag Submission Panel ---- */
	QFrame#FlagPanel {{
		background: rgba(16,20,28,0.45);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	/* Fill the right-side empty space on Overview → Submit Flag */
	QFrame#FlagSide {{
		background: rgba(16,20,28,0.28);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_lg}px;
	}}
	QLabel#FlagSideTitle {{
		font-weight: 950;
		color: rgba(245,247,255,0.92);
	}}
	QLabel#FlagSideMeta {{
		color: rgba(235,241,255,0.62);
		font-weight: 900;
	}}
	QLabel#FlagSideHint {{
		color: rgba(235,241,255,0.70);
		font-weight: 800;
		line-height: 1.25;
	}}

	/* ---- Submit Flag (top-right stacked pills) ---- */
	QLabel#FlagStatusPill,
	QLabel#FlagDifficultyPill {{
		padding: 6px 12px;
		border-radius: 999px;
		font-weight: 950;
		letter-spacing: 0.8px;
		background: rgba(255,255,255,0.05);
		border: 1px solid rgba(255,255,255,0.10);
		color: rgba(235,241,255,0.78);
		qproperty-alignment: AlignCenter;
	}}

	/* Status variants */
	QLabel#FlagStatusPill[variant="unsolved"] {{
		background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
			stop:0 rgba(11, 22, 36, 235),
			stop:1 rgba(8, 16, 28, 235)
		);
		color: #BFD7F2;
		border: 1px solid #2A4663;
		border-radius: 0px;              /* keep sharp HTB-ish look */
		padding: 6px 14px;
		letter-spacing: 1px;
		font-weight: 700;
	}}

	/* optional: a subtle top sheen so it doesn’t look flat */
	QLabel#FlagStatusPill[variant="unsolved"] {{
		border-top-color: #3C5F86;
	}}

	QLabel#FlagStatusPill[variant="active"] {{
		background: rgba(59, 130, 246, 0.18);
		border: 1px solid rgba(59, 130, 246, 0.55);
		color: rgb(147, 197, 253);
	}}
	QLabel#FlagStatusPill[variant="solved"] {{
		background: rgba(34,197,94,0.14);
		border: 1px solid rgba(34,197,94,0.30);
		color: rgba(34,197,94,0.95);
	}}

	/* Difficulty variants */
	QLabel#FlagDifficultyPill[variant="easy"] {{
		background: rgba(34,197,94,0.14);
		border: 1px solid rgba(34,197,94,0.30);
		color: rgba(34,197,94,0.95);
	}}
	QLabel#FlagDifficultyPill[variant="medium"] {{
		background: rgba(245,197,66,0.14);
		border: 1px solid rgba(245,197,66,0.30);
		color: rgba(245,197,66,0.98);
	}}
	QLabel#FlagDifficultyPill[variant="hard"] {{
		background: rgba(239,68,68,0.14);
		border: 1px solid rgba(239,68,68,0.30);
		color: rgba(239,68,68,0.98);
	}}
	QLabel#FlagDifficultyPill[variant="master"] {{
		background: rgba(168,85,247,0.14);
		border: 1px solid rgba(168,85,247,0.30);
		color: rgba(168,85,247,0.98);
	}}
	QLabel#FlagDifficultyPill[variant="neutral"] {{
		background: rgba(255,255,255,0.04);
		border: 1px solid rgba(255,255,255,0.10);
		color: rgba(235,241,255,0.72);
	}}

	QLineEdit#FlagInput {{
		/* HTB-ish inset field: darker, cleaner, and feels "important" */
		background: rgba(7, 9, 12, 0.55);
		border: 1px solid rgba(255,255,255,0.12);
		border-radius: {r_lg}px;
		padding: {p_12}px {p_14}px;
		min-height: { _s(44, scale) }px;
		font-weight: 900;
		letter-spacing: 0.25px;
		font-family: "JetBrains Mono", "Consolas", monospace;
		color: rgba(245,247,255,0.92);
		selection-background-color: rgba(245,197,66,0.30);
	}}
	QLineEdit#FlagInput:hover {{
		background: rgba(7, 9, 12, 0.62);
		border: 1px solid rgba(255,255,255,0.18);
	}}
	QLineEdit#FlagInput:focus {{
		background: rgba(7, 9, 12, 0.72);
		border: 1px solid rgba(245,197,66,0.62);
	}}
	QLineEdit#FlagInput:disabled {{
		/* "Already solved" / locked look */
		background: rgba(255,255,255,0.03);
		border: 1px solid rgba(255,255,255,0.08);
		color: rgba(235,241,255,0.50);

	}}

	QFrame#StatCard {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.07);
		border-radius: {r_xl}px;
	}}
	QLabel#StatValue {{
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,247,255,0.95);
	}}
	QLabel#StatLabel {{
		font-weight: 850;
		color: rgba(235,241,255,0.62);
	}}

	/* ---- Browse Labs: Card Grid ---- */
	QFrame#GridHeader {{
		background: rgba(10,12,16,0.55);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}
	QLabel#GridHeadCell {{
		color: rgba(235,241,255,0.60);
		font-weight: 900;
		letter-spacing: 0.4px;
	}}
	QListView#LabsGrid {{
		background: transparent;
		border: none;
		outline: none;
	}}

	/* ---- Progress (Game UI) ---- */
	QFrame#PlayerCard, QFrame#RankTrack {{
		background: rgba(16,20,28,0.45);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	QWidget#XPBar {{
		background: rgba(255,255,255,0.08);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 999px;
	}}
	QWidget#XPFill {{
		background: rgba(245,197,66,0.70);
		border-radius: 999px;
	}}

	QLabel#RankName {{
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}

	QPushButton#FilterPill {{
		background: rgba(16,20,28,0.45);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 999px;
		padding: 7px 12px;
		font-weight: 900;
		color: rgba(235,241,255,0.78);
	}}
	QPushButton#FilterPill:hover {{
		border: 1px solid rgba(255,255,255,0.16);
		background: rgba(16,20,28,0.65);
		color: rgba(245,247,255,0.92);
	}}
	QPushButton#FilterPill:checked {{
		background: rgba(245,197,66,0.16);
		border: 1px solid rgba(245,197,66,0.32);
		color: rgba(245,247,255,0.95);
	}}

	QFrame#QuestRow {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}
	QFrame#QuestRow:hover {{
		border: 1px solid rgba(255,255,255,0.14);
		background: rgba(16,20,28,0.55);
	}}

	QLabel#QuestDot {{
		font-size: 14px;
		padding-top: 1px;
		color: rgba(235,241,255,0.35);
	}}
	QLabel#QuestDot[variant="easy"] {{ color: rgba(34,197,94,0.95); }}
	QLabel#QuestDot[variant="medium"] {{ color: rgba(245,197,66,0.95); }}
	QLabel#QuestDot[variant="hard"] {{ color: rgba(239,68,68,0.95); }}
	QLabel#QuestDot[variant="master"] {{ color: rgba(168,85,247,0.95); }}

	QLabel#QuestTitle {{
		font-weight: 950;
		color: rgba(245,247,255,0.95);
	}}
	QLabel#QuestMeta {{
		color: rgba(235,241,255,0.58);
		font-weight: 800;
	}}

	QLabel#QuestPill {{
		background: rgba(255,255,255,0.06);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 999px;
		padding: 4px 10px;
		min-width: 86px;
		font-weight: 950;
		letter-spacing: 0.6px;
		color: rgba(245,247,255,0.92);
	}}
	QLabel#QuestPill[variant="solved"] {{
		background: rgba(34,197,94,0.14);
		border: 1px solid rgba(34,197,94,0.30);
	}}
	QLabel#QuestPill[variant="active"] {{
		background: rgba(245,197,66,0.14);
		border: 1px solid rgba(245,197,66,0.30);
	}}
	QLabel#QuestPill[variant="unsolved"] {{
		background: rgba(239,68,68,0.14);
		border: 1px solid rgba(239,68,68,0.28);
	}}

	QLabel#QuestXP {{
		font-weight: 950;
		color: rgba(235,241,255,0.82);
	}}
	QLabel#QuestXP[variant="earned"] {{ color: rgba(34,197,94,0.92); }}
	QLabel#QuestXP[variant="potential"] {{ color: rgba(245,197,66,0.92); }}

	QLabel#FlagFeedback {{ color: rgba(235,241,255,0.55); }}
	QLabel#FlagFeedback[variant="error"] {{ color: rgba(239, 68, 68, 0.98); }}
	QLabel#FlagFeedback[variant="ok"] {{ color: rgba(34, 197, 94, 0.98); }}

	/* ---- Inputs ---- */
	QLineEdit, QTextEdit {{
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_12}px;
	}}
	QLineEdit:focus, QTextEdit:focus {{
		border: 1px solid rgba(245,197,66,0.55);
		background: rgba(16,20,28,0.68);
	}}

	/* Lab Detail tab content boxes should NEVER get the amber focus border */
	QLineEdit[noAmberFocus="true"]:focus,
	QTextEdit[noAmberFocus="true"]:focus {{
		border: 1px solid rgba(255,255,255,0.14);
		background: rgba(16,20,28,0.68);
	}}

	/* ---- Scrollbars (Onyx Amber) ---- */
	QAbstractScrollArea::corner {{
		background: transparent;
	}}

	QScrollBar:vertical {{
		background: rgba(10,12,16,0.30);
		width: { _s(12, scale) }px;
		margin: 0px;
		border: none;
		border-radius: { _s(8, scale) }px;
	}}
	QScrollBar::handle:vertical {{
		background: rgba(255,255,255,0.14);
		min-height: { _s(36, scale) }px;
		border-radius: { _s(8, scale) }px;
		border: 1px solid rgba(255,255,255,0.10);
	}}
	QScrollBar::handle:vertical:hover {{
		background: rgba(245,197,66,0.28);
		border: 1px solid rgba(245,197,66,0.38);
	}}
	QScrollBar::handle:vertical:pressed {{
		background: rgba(245,197,66,0.36);
		border: 1px solid rgba(245,197,66,0.48);
	}}
	QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
		height: 0px;
		background: transparent;
		border: none;
	}}
	QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
		background: transparent;
	}}

	QScrollBar:horizontal {{
		background: rgba(10,12,16,0.30);
		height: { _s(12, scale) }px;
		margin: 0px;
		border: none;
		border-radius: { _s(8, scale) }px;
	}}
	QScrollBar::handle:horizontal {{
		background: rgba(255,255,255,0.14);
		min-width: { _s(36, scale) }px;
		border-radius: { _s(8, scale) }px;
		border: 1px solid rgba(255,255,255,0.10);
	}}
	QScrollBar::handle:horizontal:hover {{
		background: rgba(245,197,66,0.28);
		border: 1px solid rgba(245,197,66,0.38);
	}}
	QScrollBar::handle:horizontal:pressed {{
		background: rgba(245,197,66,0.36);
		border: 1px solid rgba(245,197,66,0.48);
	}}
	QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
		width: 0px;
		background: transparent;
		border: none;
	}}
	QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
		background: transparent;
	}}

	/* ---- Settings (Ops Console) ---- */
	QFrame#OpsCard {{
		background: rgba(10,12,16,0.70);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}
	QLabel#OpsBadge {{
		border-radius: 22px;
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.10);
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,197,66,0.92);
	}}
	QLabel#OpsTitle {{
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,247,255,0.95);
	}}

	QFrame#SettingsPanel {{
		background: rgba(10,12,16,0.62);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	QFrame#HealthRow {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_lg}px;
	}}
	QLabel#HealthTitle {{
		font-weight: 950;
		color: rgba(245,247,255,0.95);
	}}
	QLabel#HealthMeta {{
		color: rgba(235,241,255,0.62);
		font-weight: 800;
	}}
	QLabel#HealthDot {{
		min-width: 14px;
		max-width: 14px;
		color: rgba(235,241,255,0.55);
	}}
	QLabel#HealthDot[variant="success"] {{ color: rgba(34,197,94,0.95); }}
	QLabel#HealthDot[variant="error"] {{ color: rgba(239,68,68,0.95); }}
	QLabel#HealthDot[variant="neutral"] {{ color: rgba(235,241,255,0.40); }}

	QLabel#HealthPill {{
		padding: {p_6}px {p_10}px;
		border-radius: {r_md}px;
		font-weight: 950;
		border: 1px solid rgba(255,255,255,0.10);
		background: rgba(16,20,28,0.55);
		color: rgba(245,247,255,0.92);
		min-width: { _s(84, scale) }px;
	}}
	QLabel#HealthPill[variant="success"] {{
		background: rgba(34,197,94,0.14);
		border: 1px solid rgba(34,197,94,0.30);
		color: rgba(34,197,94,0.95);
	}}
	QLabel#HealthPill[variant="error"] {{
		background: rgba(239,68,68,0.14);
		border: 1px solid rgba(239,68,68,0.30);
		color: rgba(239,68,68,0.95);
	}}
	QLabel#HealthPill[variant="neutral"] {{
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.10);
		color: rgba(235,241,255,0.72);
	}}

	QFrame#LinkCard {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_lg}px;
	}}
	QLabel#LinkTitle {{ font-weight: 950; color: rgba(245,247,255,0.95); }}
	QLabel#LinkMeta {{ color: rgba(235,241,255,0.62); font-weight: 800; }}

	/* ---- Tables ---- */
	QAbstractItemView {{
		background: rgba(16,20,28,0.35);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_lg}px;
		selection-background-color: transparent;
		outline: none;
	}}

	QAbstractItemView::item {{
		padding: {p_10}px {p_10}px;
		border: none;
	}}

	QAbstractItemView::item:selected {{
		background: transparent;
		color: rgba(245,247,255,0.95);
	}}

	QHeaderView::section {{
		background: transparent;
		color: rgba(235,241,255,0.72);
		font-weight: 900;
		border: none;
		padding: 10px 10px;
	}}
	QHeaderView {{ background: transparent; }}
	QTableCornerButton::section {{
		background: transparent;
		border: none;
	}}

	/* Labs tables should feel embedded in the surface (no hard outer frame line) */
	QTableView#LabsTable,
	QTableWidget#LabsTable {{
		border: none;
		background: transparent;
		gridline-color: transparent;
		selection-background-color: transparent;
		outline: none;
	}}

	QTableWidget#LabsTable::item:selected {{
		background: transparent;
	}}

	QTableView#LabsTable::item:focus,
	QTableWidget#LabsTable::item:focus,
	QAbstractItemView::item:focus {{
		outline: none;
		border: none;
	}}

	QTableView#LabsTable::item:selected,
	QTableWidget#LabsTable::item:selected,
	QAbstractItemView::item:selected {{
		background: transparent;
	}}

	/* ---- Pills ---- */
	QFrame#Pill {{
		border-radius: 999px;
		padding: 0px;
		background: #000000;                          /* TRUE BLACK */
		border: 1px solid rgba(255,255,255,0.16);     /* makes it readable */
	}}

	QLabel#PillText {{
		background: transparent;                      /* don't lighten the fill */
		padding: 6px 12px;
		font-weight: 900;
		color: rgba(245,247,255,0.92);
	}}

	/* Optional: a subtle "pill edge" highlight without making it grey */
	QFrame#Pill::before {{ /* Qt ignores ::before; leave this out if you tried it */
	}}

	/* Variants: keep fill BLACK, only change border + text */
	QFrame#Pill[variant="warn"] {{
		background: #000000;
		border: 1px solid rgba(245,197,66,0.55);
	}}
	QFrame#Pill[variant="success"] {{
		background: #000000;
		border: 1px solid rgba(34,197,94,0.55);
	}}

	QFrame#Pill[variant="warn"] QLabel#PillText {{ color: rgba(245,197,66,0.98); }}
	QFrame#Pill[variant="success"] QLabel#PillText {{ color: rgba(34,197,94,0.98); }}

	/* ---- Combobox (Filters) ---- */
	QComboBox#FilterCombo {{
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_12}px;
		padding-right: {p_12 + 44}px;
		font-weight: 900;
		color: rgba(235,241,255,0.86);
	}}
	QComboBox#FilterCombo:hover {{
		background: rgba(16,20,28,0.70);
		border: 1px solid rgba(255,255,255,0.16);
	}}
	
	/* when popup is open */
	QComboBox#FilterCombo:on {{
		background: rgba(16,20,28,0.72);
		border: 1px solid rgba(255,255,255,0.16);
	}}
	QComboBox#FilterCombo:focus {{
		border: 1px solid rgba(255,255,255,0.16);
		background: rgba(16,20,28,0.70);
	}}

	QComboBox#FilterCombo::drop-down {{
		subcontrol-origin: padding;
		subcontrol-position: top right;
		width: 40px;
		border-left: 1px solid rgba(255,255,255,0.10);
		border-top-right-radius: {r_lg}px;
		border-bottom-right-radius: {r_lg}px;
		background: rgba(16,20,28,0.62);
	}}

	QComboBox#FilterCombo::drop-down:hover {{
		background: rgba(16,20,28,0.72);
	}}

	QComboBox#FilterCombo::down-arrow {{
		image: none; /* we draw our own chevron via OnyxComboStyle */
	}}

	/* ---- REAL combobox popup window/frame (this is the white thing) ---- */
	QFrame#qt_combobox_popup {{
		background: rgba(10,12,16,0.96);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 12px;
		padding: 6px;
	}}

	/* Everything inside the popup must be transparent so ONLY the frame paints */
	QFrame#qt_combobox_popup QAbstractScrollArea,
	QFrame#qt_combobox_popup QWidget#qt_scrollarea_viewport,
	QFrame#qt_combobox_popup QAbstractItemView {{
		background: transparent;
		border: none;
		outline: none;
	}}

	/* Item styling */
	QFrame#qt_combobox_popup QAbstractItemView::item {{
		padding: 10px 12px;
		border-radius: 10px;
		background: transparent;
		color: rgba(235,241,255,0.92);
		font-weight: 850;
	}}

	QFrame#qt_combobox_popup QAbstractItemView::item:hover {{
		background: rgba(255,255,255,0.06);
	}}

	QFrame#qt_combobox_popup QAbstractItemView::item:selected {{
		background: rgba(245,197,66,0.18);
		color: rgba(245,247,255,0.96);
	}}

	/* ---- Combo popup (force BLACK bg + WHITE text, no fighting with global QAbstractItemView) ---- */
	QListView#ComboPopup {{
		background: rgba(10,12,16,0.96);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 12px;
		padding: 6px;
		outline: none;
		color: rgba(235,241,255,0.92);
		selection-background-color: transparent;
	}}
	QListView#ComboPopup QWidget#qt_scrollarea_viewport {{
		background: rgba(10,12,16,0.96);
	}}
	QListView#ComboPopup::item {{
		padding: 10px 12px;
		border-radius: 10px;
		background: transparent;
		color: rgba(235,241,255,0.92);
		font-weight: 850;
	}}
	QListView#ComboPopup::item:hover {{
		background: rgba(255,255,255,0.06);
	}}
	QListView#ComboPopup::item:selected {{
		background: rgba(245,197,66,0.18);
		color: rgba(245,247,255,0.96);
	}}

	/* ---- Combo popup WINDOW (what's behind the list) ---- */
	QComboBoxPrivateContainer {{
		background: rgba(10,12,16,0.96);
		border: none;
	}}

	QComboBoxPrivateContainer QAbstractScrollArea {{
		background: rgba(10,12,16,0.96);
		border: none;
	}}

	QComboBoxPrivateContainer QWidget#qt_scrollarea_viewport {{
		background: rgba(10,12,16,0.96);
		border: none;
	}}

	QComboBoxPrivateContainer QFrame {{
		background: rgba(10,12,16,0.96);
		border: none;
	}}

	/* ---- Lab Detail ---- */
	QFrame#LabHero {{
		background: rgba(10,12,16,0.70);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	/* ---- Overview Tab: Simple Briefing + Flag ---- */
	QScrollArea#OverviewScroll {{
		background: transparent;
		border: none;
	}}
	QWidget#OverviewRoot {{
		background: transparent;
	}}

	QFrame#StoryCard {{
		background: rgba(10,12,16,0.62);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}
	QLabel#StoryTitle {{
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#StoryBody {{
		color: rgba(235,241,255,0.82);
		font-weight: 800;
		line-height: 1.25;
	}}

	QFrame#FlagPanel {{
		background: rgba(10,12,16,0.62);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}

	QLabel#FlagTitle {{
		font-size: {h2}px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#FlagHint {{
		color: rgba(235,241,255,0.60);
		font-weight: 850;
	}}
	QLabel#FlagSolvedPill {{
		padding: 6px 12px;
		border-radius: 999px;
		font-weight: 950;
		letter-spacing: 0.8px;
		background: rgba(34,197,94,0.14);
		border: 1px solid rgba(34,197,94,0.30);
		color: rgba(34,197,94,0.95);
	}}

	/* ---- Info Tab (Gorgeous) ---- */
	QScrollArea#InfoScroll {{
		background: transparent;
		border: none;
	}}
	QWidget#InfoRoot {{
		background: transparent;
	}}

	QFrame#InfoSummaryCard {{
		background: rgba(10,12,16,0.62);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: 18px;
	}}

	QLabel#InfoSummaryTitle {{
		font-weight: 950;
		color: rgba(245,247,255,0.95);
		font-size: 16px;
	}}

	QLabel#InfoSummarySub {{
		color: rgba(235,241,255,0.60);
		font-weight: 850;
	}}

	QLabel#InfoPill {{
		padding: 6px 12px;
		border-radius: 999px;
		font-weight: 950;
		letter-spacing: 0.8px;
		color: rgba(245,197,66,0.96);
		background: rgba(245,197,66,0.10);
		border: 1px solid rgba(245,197,66,0.24);
	}}

	QFrame#InfoCard {{
		background: rgba(10,12,16,0.62);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: 18px;
	}}

	QLabel#InfoSectionTitle {{
		font-weight: 950;
		color: rgba(245,247,255,0.94);
	}}

	QFrame#InfoDivider {{
		background: rgba(255,255,255,0.06);
	}}

	QFrame#InfoRow {{
		background: rgba(16,20,28,0.35);
		border: 1px solid rgba(255,255,255,0.07);
		border-radius: 16px;
	}}
	QFrame#InfoRow:hover {{
		background: rgba(16,20,28,0.50);
		border: 1px solid rgba(255,255,255,0.10);
	}}

	QLabel#InfoKey {{
		color: rgba(235,241,255,0.55);
		font-weight: 900;
		min-width: 98px;
	}}

	QLabel#InfoValue {{
		color: rgba(235,241,255,0.92);
		font-weight: 900;
	}}

	QLabel#InfoMono {{
		font-family: "JetBrains Mono", "Consolas", monospace;
		color: rgba(235,241,255,0.88);
		font-weight: 850;
	}}

	QToolButton#InfoCopyBtn, QToolButton#InfoOpenBtn {{
		border-radius: 10px;
		border: 1px solid rgba(255,255,255,0.08);
		background: rgba(255,255,255,0.03);
	}}
	QToolButton#InfoCopyBtn:hover, QToolButton#InfoOpenBtn:hover {{
		border: 1px solid rgba(255,255,255,0.14);
		background: rgba(255,255,255,0.06);
	}}

	QLabel#InfoDesc {{
		color: rgba(235,241,255,0.80);
		font-weight: 800;
		line-height: 1.25;
	}}

	QLabel#HeroTitle {{
		font-size: {h1}px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#HeroMeta {{
		color: rgba(235,241,255,0.62);
		font-weight: 800;
	}}
	QLabel#LabIcon {{
		border-radius: 23px;
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.08);
	}}

	QFrame#ConnBar {{
		background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
		  stop:0 rgba(245,197,66,0.12),
		  stop:0.35 rgba(10,12,16,0.86),
		  stop:1 rgba(10,12,16,0.74)
		);
		border: 1px solid rgba(255,255,255,0.12);
		border-radius: {r_xl}px;
	}}
	QFrame#ConnBar:hover {{
		border: 1px solid rgba(255,255,255,0.12);
	}}

	/* ---- ConnBar action buttons: Stop (danger) + Reset (amber) ---- */
	QPushButton#ConnStopBtn {{
		background: rgba(239,68,68,0.10);
		border: 1px solid rgba(239,68,68,0.26);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_14}px;
		font-weight: 950;
		color: rgba(245,247,255,0.92);
	}}
	QPushButton#ConnStopBtn:hover {{
		background: rgba(239,68,68,0.16);
		border: 1px solid rgba(239,68,68,0.34);
	}}
	QPushButton#ConnStopBtn:pressed {{
		background: rgba(239,68,68,0.20);
	}}
	QPushButton#ConnStopBtn:disabled {{
		background: rgba(255,255,255,0.02);
		border: 1px solid rgba(255,255,255,0.06);
		color: rgba(235,241,255,0.25);
	}}

	QPushButton#ConnResetBtn {{
		background: rgba(245,197,66,0.10);
		border: 1px solid rgba(245,197,66,0.26);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_14}px;
		font-weight: 950;
		color: rgba(245,247,255,0.92);
	}}
	QPushButton#ConnResetBtn:hover {{
		background: rgba(245,197,66,0.16);
		border: 1px solid rgba(245,197,66,0.34);
	}}
	QPushButton#ConnResetBtn:pressed {{
		background: rgba(245,197,66,0.20);
	}}
	QPushButton#ConnResetBtn:disabled {{
		background: rgba(255,255,255,0.02);
		border: 1px solid rgba(255,255,255,0.06);
		color: rgba(235,241,255,0.25);
	}}

	QPushButton#ConnStartBig {{
		background: rgba(245,197,66,0.16);
		border: 1px solid rgba(245,197,66,0.32);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_16}px;
		font-weight: 950;
		color: rgba(245,247,255,0.95);
	}}
	QPushButton#ConnStartBig:hover {{
		background: rgba(245,197,66,0.22);
		border: 1px solid rgba(245,197,66,0.40);
	}}

	QLabel#ConnValue {{
		background: transparent;
		border: none;
		padding: 0px;
		color: rgba(245,197,66,0.96);
		font-weight: 950;
	}}

	QPushButton#PrimaryButton {{
		background: rgba(245,197,66,0.16);
		border: 1px solid rgba(245,197,66,0.32);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_14}px;
		font-weight: 900;
	}}
	QPushButton#PrimaryButton:hover {{
		background: rgba(245,197,66,0.22);
		border: 1px solid rgba(245,197,66,0.40);
	}}

	QPushButton#GhostButton {{
		background: rgba(16,20,28,0.55);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: {r_lg}px;
		padding: {p_10}px {p_14}px;
		font-weight: 900;
	}}
	QPushButton#GhostButton:hover {{
		border: 1px solid rgba(255,255,255,0.16);
		background: rgba(16,20,28,0.72);
	}}

	QTabWidget::pane {{
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
		background: rgba(10,12,16,0.62);
		top: -1px;
	}}
	QTabBar::tab {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.08);
		border-bottom: none;
		border-top-left-radius: {r_lg}px;
		border-top-right-radius: {r_lg}px;
		padding: {p_10}px {p_16}px;
		min-width: { _s(120, scale) }px;
		margin-right: 6px;
		font-weight: 900;
		color: rgba(235,241,255,0.70);
	}}

	QTabBar::tab:first {{
		margin-left: 6px;
	}}

	QTabBar::tab:selected {{
		background: rgba(245,197,66,0.14);
		border: 1px solid rgba(245,197,66,0.30);
		color: rgba(245,247,255,0.95);
	}}

	/* ---- Command Palette ---- */
	QFrame#PaletteShell {{
		background: rgba(10,12,16,0.96);
		border: 1px solid rgba(255,255,255,0.14);
		border-radius: {r_xl}px;
	}}
	QListWidget#PaletteList {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: {r_lg}px;
		padding: 8px;
		outline: none;
	}}
	QListWidget#PaletteList::item {{
		background: transparent;
		border-radius: 12px;
		padding: 10px 10px;
		color: rgba(235,241,255,0.88);
	}}
	QListWidget#PaletteList::item:selected {{
		background: rgba(245,197,66,0.14);
		border: 1px solid rgba(245,197,66,0.26);
		color: rgba(245,247,255,0.95);
	}}

	QFrame#BreadcrumbBar {{
		background: rgba(10,12,16,0.55);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: 16px;
	}}

	QLabel#CrumbSep {{
		color: rgba(235,241,255,0.45);
		font-weight: 800;
		padding: 0px 2px;
	}}
	QLabel#CrumbCurrent {{
		color: rgba(245,247,255,0.92);
		font-weight: 950;
		letter-spacing: 0.2px;
	}}

	QToolButton#CrumbBtn {{
		background: transparent;
		border: none;
		color: rgba(245,197,66,0.92);
		font-weight: 950;
		padding: 6px 6px;
	}}

	QToolButton#CrumbBtn:hover {{ color: rgba(255,209,102,0.96); }}

	/* ---- Lab detail split & tabs (smoother, less "boxed") ---- */
	QSplitter#DetailSplit::handle:horizontal {{
		background: transparent;
		width: 8px;
	}}
	QSplitter#DetailSplit::handle:horizontal:hover {{
		background: rgba(255,255,255,0.04);
		border-radius: 10px;
	}}
	QFrame#DetailLeft, QFrame#DetailRight {{
		background: transparent;
		border: none;
	}}
	QTabWidget#DetailTabs::pane {{
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
		background: rgba(10,12,16,0.68);
		top: -1px;
	}}

	QFrame#TabsCorner {{
		background: transparent;
		border: none;
	}}

	/* ---- Grid header (Browse Labs cards) ---- */
	QFrame#GridHeader {{
		background: transparent;
		border: none;
	}}
	QLabel#GridHeaderLabel {{
		color: rgba(235,241,255,0.62);
		font-weight: 900;
	}}

	/* ---- Scrollbars (Onyx Amber) ---- */
	QScrollBar:vertical {{
		background: transparent;
		width: 12px;
		margin: 2px 2px 2px 2px;
	}}
	QScrollBar::handle:vertical {{
		background: rgba(255,255,255,0.14);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 6px;
		min-height: 26px;
	}}
	QScrollBar::handle:vertical:hover {{
		background: rgba(245,197,66,0.22);
		border: 1px solid rgba(245,197,66,0.26);
	}}
	QScrollBar::handle:vertical:pressed {{
		background: rgba(245,197,66,0.30);
		border: 1px solid rgba(245,197,66,0.34);
	}}
	QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
		height: 0px;
		background: transparent;
		border: none;
	}}
	QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
		background: transparent;
	}}

	QScrollBar:horizontal {{
		background: transparent;
		height: 12px;
		margin: 2px 2px 2px 2px;
	}}
	QScrollBar::handle:horizontal {{
		background: rgba(255,255,255,0.14);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 6px;
		min-width: 26px;
	}}
	QScrollBar::handle:horizontal:hover {{
		background: rgba(245,197,66,0.22);
		border: 1px solid rgba(245,197,66,0.26);
	}}
	QScrollBar::handle:horizontal:pressed {{
		background: rgba(245,197,66,0.30);
		border: 1px solid rgba(245,197,66,0.34);
	}}
	QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
		width: 0px;
		background: transparent;
		border: none;
	}}
	QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
		background: transparent;
	}}

	/* =========================
	   Toasts (fix invisible bg)
	   ========================= */
	#ToastCard {{
		background: rgba(14, 14, 16, 0.95);
		border: 1px solid rgba(255, 255, 255, 0.10);
		border-radius: 14px;
	}}
	#ToastTitle {{
		color: rgba(255, 255, 255, 0.94);
		font-size: {small}px;
		font-weight: 800;
	}}
	#ToastBody {{
		color: rgba(255, 255, 255, 0.78);
		font-size: {small}px;
	}}
	#ToastDot {{
		font-size: {small}px;
	}}

	#ToastCard[variant="success"] {{
		border: 1px solid rgba(73, 224, 123, 0.26);
	}}
	#ToastCard[variant="success"] #ToastDot {{
		color: rgba(73, 224, 123, 0.95);
	}}

	#ToastCard[variant="error"] {{
		border: 1px solid rgba(255, 99, 99, 0.30);
	}}
	#ToastCard[variant="error"] #ToastDot {{
		color: rgba(255, 99, 99, 0.95);
	}}

	#ToastCard[variant="warn"] {{
		border: 1px solid rgba(245, 197, 66, 0.34);
	}}
	#ToastCard[variant="warn"] #ToastDot {{
		color: rgba(245, 197, 66, 0.95);
	}}

	#ToastCard[variant="info"] {{
		border: 1px solid rgba(91, 164, 255, 0.34);
	}}
	#ToastCard[variant="info"] #ToastDot {{
		color: rgba(91, 164, 255, 0.95);
	}}

	/* =========================
	   Lab solved celebration
	   ========================= */
	#SolveOverlay {{
		background: rgba(0, 0, 0, 0.72);
	}}
	#SolveCard {{
		background: rgba(14, 14, 16, 0.96);
		border: 1px solid rgba(255, 255, 255, 0.14);
		border-radius: 22px;
	}}
	#SolveTitle {{
		color: rgba(255, 255, 255, 0.96);
		font-size: {h1}px;
		font-weight: 900;
		letter-spacing: 3px;
	}}
	#SolveSubtitle {{
		color: rgba(255, 255, 255, 0.88);
		font-size: {h2}px;
		font-weight: 800;
	}}
	#SolveMeta {{
		color: rgba(255, 255, 255, 0.74);
		font-size: {small}px;
		font-weight: 800;
	}}
	#SolveCover {{
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid rgba(255, 255, 255, 0.10);
		border-radius: 14px;
		padding: 8px;
	}}
	#SolveContinue {{
		background: rgba(255, 196, 62, 0.18);
		border: 1px solid rgba(255, 196, 62, 0.40);
		color: rgba(255, 255, 255, 0.92);
		padding: 10px 18px;
		border-radius: 12px;
		font-weight: 900;
	}}
	#SolveContinue:hover {{
		background: rgba(255, 196, 62, 0.26);
		border: 1px solid rgba(255, 196, 62, 0.52);
	}}

	/* Dialog panels */
	QFrame#Panel {{
		background: rgba(255,255,255,0.04);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 18px;
	}}
	QListWidget#InstallLabsList {{
		background: transparent;
		border: none;
		padding: 4px;
	}}
	QListWidget#InstallLabsList::item {{
		padding: 10px 8px;
		border-radius: 12px;
		color: rgba(255,255,255,0.88);
	}}
	QListWidget#InstallLabsList::item:hover {{
		background: rgba(245,197,66,0.10);
	}}

	/* ---- Profile (Mission Control) ---- */
	QWidget#ProfileRoot {{
		background: transparent;
	}}
	QScrollArea#ProfileScroll {{
		background: transparent;
		border: none;
	}}
	QWidget#ProfileContent {{
		background: transparent;
	}}
	QFrame#ProfileHero {{
		background: rgba(16,20,28,0.52);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: {r_xl}px;
	}}
	QLabel#ProfileAvatar {{
		min-width: 56px;
		max-width: 56px;
		min-height: 56px;
		max-height: 56px;
		border-radius: 28px;
		background: rgba(245,197,66,0.12);
		border: 1px solid rgba(245,197,66,0.25);
		color: rgba(245,247,255,0.95);
		font-weight: 950;
		font-size: 16px;
	}}
	QLabel#ProfileUsername {{
		font-size: {h1}px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#ProfileRankLine {{
		font-size: 14px;
		font-weight: 800;
		color: rgba(235,241,255,0.78);
	}}
	QLabel#ProfileNextLine {{
		font-size: 13px;
		font-weight: 750;
		color: rgba(235,241,255,0.62);
	}}
	QFrame#ProfileXPBar {{
		background: rgba(255,255,255,0.08);
		border: 1px solid rgba(255,255,255,0.10);
		border-radius: 999px;
	}}
	QFrame#ProfileXPFill {{
		background: rgba(245,197,66,0.78);
		border-radius: 999px;
	}}
	QLabel#ProfileXPText {{
		font-size: 12px;
		font-weight: 850;
		color: rgba(235,241,255,0.70);
	}}
	QPushButton#ProfileLogoutBtn {{
		background: rgba(10,12,16,0.55);
		border: 1px solid rgba(245,197,66,0.22);
		border-radius: 999px;
		padding: 7px 14px;
		font-weight: 950;
		letter-spacing: 0.2px;
		color: rgba(235,241,255,0.90);
		min-height: 34px;
	}}
	QPushButton#ProfileLogoutBtn:hover {{
		background: rgba(16,20,28,0.70);
		border: 1px solid rgba(245,197,66,0.42);
		color: rgba(245,247,255,0.96);
	}}

	QPushButton#ProfileLogoutBtn:pressed {{
		background: rgba(8,10,13,0.80);
		border: 1px solid rgba(245,197,66,0.34);
		padding-top: 8px;
		padding-bottom: 6px;
	}}
	QPushButton#ProfileLogoutBtn:disabled {{
		background: rgba(255,255,255,0.02);
		border: 1px solid rgba(255,255,255,0.06);
		color: rgba(235,241,255,0.22);
	}}

	/* =========================
	   Sidebar locked/disabled look
	   ========================= */

	QPushButton#NavButton:disabled {{
		/* visibly locked: muted + slightly “fogged” */
		color: rgba(235, 242, 255, 0.35);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid rgba(255, 255, 255, 0.06);
	}}

	QPushButton#NavButton[locked="true"] {{
		/* if you want an even stronger locked cue while disabled */
		background: rgba(255, 255, 255, 0.035);
		border: 1px dashed rgba(255, 255, 255, 0.10);
	}}

	QPushButton#NavButton[locked="true"]::after {{
		/* Qt style sheets don’t support ::after content reliably across platforms.
		   This is intentionally empty; leaving block here so you don’t assume it works. */
	}}

	/*QFrame#ProfileBadge[locked="true"] {{
		background: rgba(255, 255, 255, 0.03);
		border: 1px dashed rgba(255, 255, 255, 0.10);
	}}

	QFrame#ProfileBadge[locked="true"] QLabel {{
		color: rgba(235, 242, 255, 0.35);
	}}*/

	QFrame#ProfileKPI {{
		background: rgba(16,20,28,0.42);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}
	QLabel#KPIValue {{
		font-size: 22px;
		font-weight: 950;
		color: rgba(245,247,255,0.96);
	}}
	QLabel#KPILabel {{
		font-size: 12px;
		font-weight: 850;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: rgba(235,241,255,0.52);
	}}
	QFrame#ActivityPanel {{
		background: rgba(16,20,28,0.40);
		border: 1px solid rgba(255,255,255,0.08);
		border-radius: {r_xl}px;
	}}
	QLabel#ActivityHeader {{
		font-size: 14px;
		font-weight: 950;
		color: rgba(245,247,255,0.92);
	}}
	QFrame#ActivityRow {{
		background: rgba(255,255,255,0.03);
		border: 1px solid rgba(255,255,255,0.06);
		border-radius: 16px;
	}}
	QFrame#ActivityRow:hover {{
		background: rgba(255,255,255,0.05);
		border: 1px solid rgba(255,255,255,0.10);
	}}
	QLabel#ActivityIcon {{
		min-width: 36px;
		max-width: 36px;
		min-height: 36px;
		max-height: 36px;
		border-radius: 10px;
		background: rgba(255,255,255,0.06);
		border: 1px solid rgba(255,255,255,0.08);
	}}
	QLabel#ActivityText {{
		font-size: 13px;
		font-weight: 900;
		color: rgba(245,247,255,0.90);
	}}
	QLabel#ActivityMeta {{
		font-size: 12px;
		font-weight: 750;
		color: rgba(235,241,255,0.55);
	}}
	QLabel#ActivityXP {{
		font-size: 13px;
		font-weight: 950;
		color: rgba(245,197,66,0.95);
	}}
	QLabel#MemberSince {{
		font-size: 12px;
		font-weight: 850;
		color: rgba(235,241,255,0.50);
		padding-left: 4px;
	}}
	"""
