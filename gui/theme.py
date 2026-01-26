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

    p_6 = _s(6, scale)
    p_8 = _s(8, scale)
    p_10 = _s(10, scale)
    p_12 = _s(12, scale)
    p_14 = _s(14, scale)
    p_16 = _s(16, scale)
    p_18 = _s(18, scale)

    return f"""
    QWidget {{
        background: #07090C;
        color: rgba(235,241,255,0.90);
        font-family: Inter, "Segoe UI", Arial;
        font-size: {base_font}px;
    }}

    QLabel {{
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
        background: rgba(10,12,16,0.78);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: {r_xl}px;
    }}

    QToolButton#TopNavBtn {{
        background: rgba(16,20,28,0.55);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 12px;
        padding: 6px 10px;
        font-weight: 900;
        color: rgba(235,241,255,0.86);
    }}
    QToolButton#TopNavBtn:hover {{ border: 1px solid rgba(255,255,255,0.16); background: rgba(16,20,28,0.72); }}
    QToolButton#TopNavBtn:disabled {{ color: rgba(235,241,255,0.28); border: 1px solid rgba(255,255,255,0.06); background: rgba(16,20,28,0.30); }}

    QFrame#RunPill {{
        background: rgba(16,20,28,0.55);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
    }}
    QLabel#RunState {{
        background: rgba(239,68,68,0.14);
        border: 1px solid rgba(239,68,68,0.30);
        border-radius: 12px;
        padding: 4px 10px;
        font-weight: 950;
        letter-spacing: 0.5px;
        color: rgba(245,247,255,0.92);
    }}
    QLabel#RunState[variant="running"] {{
        background: rgba(34,197,94,0.14);
        border: 1px solid rgba(34,197,94,0.30);
    }}
    QLabel#RunHint {{ color: rgba(235,241,255,0.62); font-weight: 800; padding-left: 6px; padding-right: 10px; }}

    QLineEdit#SearchBox {{
        background: rgba(16,20,28,0.60);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
        padding: {p_10}px {p_12}px;
        selection-background-color: rgba(245,197,66,0.30);
    }}
    QLineEdit#SearchBox:focus {{
        border: 1px solid rgba(245,197,66,0.55);
        background: rgba(16,20,28,0.72);
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

    QFrame#DockerBadge {{
        background: rgba(16,20,28,0.55);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: {r_md}px;
    }}
    QLabel#DockerBadgeText {{
        font-weight: 850;
        color: rgba(235,241,255,0.78);
        padding: {p_8}px {p_10}px;
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
    QLineEdit#FlagInput {{
        background: rgba(16,20,28,0.55);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: {r_lg}px;
        padding: {p_10}px {p_12}px;
        min-height: { _s(38, scale) }px;
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

    /* ---- Progress (Game UI) ---- */
    QFrame#PlayerCard, QFrame#RankTrack {{
        background: rgba(16,20,28,0.45);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: {r_xl}px;
    }}

    QFrame#XPBar {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 999px;
    }}
    QFrame#XPFill {{
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
        border-radius: {r_md}px;
        padding: 0px;
        border: 1px solid rgba(255,255,255,0.10);
        background: rgba(16,20,28,0.55);
    }}
    QLabel#PillText {{
        padding: {p_6}px {p_10}px;
        font-weight: 900;
        color: rgba(245,247,255,0.92);
    }}

    QFrame#Pill[variant="warn"] {{
        background: rgba(245,197,66,0.16);
        border: 1px solid rgba(245,197,66,0.30);
    }}

    QWidget#CellWrap {{ background: transparent; }}

    QFrame#Pill[variant="success"] {{
        background: rgba(34,197,94,0.14);
        border: 1px solid rgba(34,197,94,0.30);
    }}

    QFrame#Pill[variant="warn"] QLabel#PillText {{ color: rgba(245,197,66,0.95); }}
    QFrame#Pill[variant="success"] QLabel#PillText {{ color: rgba(34,197,94,0.95); }}

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
        border: 1px solid rgba(245,197,66,0.55);
    }}
    QComboBox#FilterCombo:focus {{
        border: 1px solid rgba(245,197,66,0.55);
        background: rgba(16,20,28,0.72);
    }}

    QComboBox#FilterCombo:on {{
        /* when popup is open (prevents native grey "pressed" look) */
        border: 1px solid rgba(245,197,66,0.55);
        background: rgba(16,20,28,0.72);
    }}
    QComboBox#FilterCombo::down-arrow {{
        image: none; /* we draw our own chevron via OnyxComboStyle */
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

    /* triangle arrow (explicit, so it never disappears) */
    QComboBox#FilterCombo::down-arrow {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        right: {p_12}px;
        width: 0px;
        height: 0px;
        border-left: 6px solid transparent;
        border-right: 6px solid transparent;
        border-top: 8px solid rgba(235,241,255,0.72);
    }}
    QComboBox#FilterCombo::down-arrow:disabled {{
        border-top-color: rgba(235,241,255,0.28);
    }}

    /* popup container (remove the outer grey frame) */
    QComboBoxPrivateContainer {{
        background: transparent;
        border: none;
        padding: 0px;
    }}

    /* kill the inherited frame/border from QAbstractItemView/QAbstractScrollArea */
    QComboBoxPrivateContainer QAbstractScrollArea {{
        background: transparent;
        border: none;
    }}

    QComboBoxPrivateContainer QAbstractItemView {{
        background: rgba(10,12,16,0.96);
        border: none;                 /* <-- removes grey outline */
        outline: none;
        padding: 6px;
        border-radius: 12px;
        selection-background-color: rgba(245,197,66,0.18);
        selection-color: rgba(245,247,255,0.96);
    }}

    QComboBoxPrivateContainer QAbstractItemView::item {{
        padding: 10px 12px;
        border-radius: 10px;
        background: transparent;
        color: rgba(235,241,255,0.88);
    }}

    QComboBoxPrivateContainer QAbstractItemView::item:hover {{
        background: rgba(255,255,255,0.06);
    }}

    QComboBoxPrivateContainer QAbstractItemView::item:selected {{
        background: rgba(245,197,66,0.18);
        color: rgba(245,247,255,0.96);
    }}

    QComboBox#FilterCombo QAbstractItemView {{
        background: rgba(10,12,16,0.96);
        border: none;
        border-radius: 12px;
        outline: none;
        padding: 6px;
        color: rgba(235,241,255,0.88);
        selection-background-color: rgba(245,197,66,0.18);
        selection-color: rgba(245,247,255,0.96);
    }}
    QComboBox#FilterCombo QAbstractItemView::item {{
        padding: 9px 10px;
        border-radius: 10px;
        background: transparent;
    }}
    QComboBox#FilterCombo QAbstractItemView::item:hover {{
        background: rgba(255,255,255,0.06);
    }}
    QComboBox#FilterCombo QAbstractItemView::item:selected {{
        background: rgba(245,197,66,0.14);
        background: rgba(245,197,66,0.18);
        color: rgba(245,247,255,0.96);
    }}

    /* Popup list */
    QComboBox QAbstractItemView {{
        background: rgba(10,12,16,0.96);
        border: none;
        border-radius: 12px;
        selection-background-color: rgba(245,197,66,0.18);
        selection-color: rgba(245,247,255,0.96);
        outline: none;
    }}

    QComboBox QAbstractItemView::item {{
        padding: 10px 12px;
        border-radius: 10px;
        color: rgba(235,241,255,0.88);
    }}

    QComboBox QAbstractItemView::item:selected {{
        background: rgba(245,197,66,0.18);
        color: rgba(245,247,255,0.96);
    }}


    /* ---- Lab Detail ---- */
    QFrame#LabHero {{
        background: rgba(10,12,16,0.70);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: {r_xl}px;
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
    QToolButton#CrumbBtn {{
        background: transparent;
        border: none;
        color: rgba(245,197,66,0.92);
        font-weight: 950;
        padding: 6px 6px;
    }}
    QToolButton#CrumbBtn:hover {{ color: rgba(255,209,102,0.96); }}
    """
