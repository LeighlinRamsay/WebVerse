from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional, Tuple, List, Dict, Any

from webverse.core.xp import base_xp_for_difficulty


RANKS: List[Tuple[str, int]] = [
    ("Bronze I", 0),
    ("Bronze II", 300),
    ("Bronze III", 700),
    ("Silver I", 1200),
    ("Silver II", 2000),
    ("Silver III", 3000),
    ("Gold I", 4500),
    ("Gold II", 6500),
    ("Gold III", 9000),
    ("Platinum", 12000),
    ("Diamond", 16000),
    ("Master", 21000),
]


def rank_for_xp(xp: int) -> Tuple[str, int, Optional[str], Optional[int]]:
    cur_name, cur_floor = RANKS[0]
    next_name, next_floor = None, None
    for i, (name, floor) in enumerate(RANKS):
        if xp >= floor:
            cur_name, cur_floor = name, floor
            if i + 1 < len(RANKS):
                next_name, next_floor = RANKS[i + 1]
            else:
                next_name, next_floor = None, None
        else:
            break
    return cur_name, cur_floor, next_name, next_floor


def total_xp(labs: Iterable[Any], progress_map: Dict[str, dict]) -> int:
    xp = 0
    for lab in labs:
        lab_id = str(getattr(lab, "id", ""))
        p = progress_map.get(lab_id, {}) or {}
        if p.get("solved_at"):
            xp += base_xp_for_difficulty(getattr(lab, "difficulty", "") or "")
    return int(xp)


def solved_count(labs: Iterable[Any], progress_map: Dict[str, dict]) -> int:
    n = 0
    for lab in labs:
        lab_id = str(getattr(lab, "id", ""))
        p = progress_map.get(lab_id, {}) or {}
        if p.get("solved_at"):
            n += 1
    return int(n)


def completion_percent(total: int, solved: int) -> int:
    total = int(total or 0)
    solved = int(solved or 0)
    if total <= 0:
        return 0
    return int(round((solved / max(1, total)) * 100.0))


def _parse_iso_dt(value: str) -> Optional[datetime]:
    try:
        if not value:
            return None
        dt = datetime.fromisoformat(str(value))
        try:
            if dt.tzinfo is not None:
                dt = dt.astimezone()
        except Exception:
            pass
        return dt
    except Exception:
        return None


def solve_streak_days(progress_map: Dict[str, dict]) -> int:
    dates = set()
    for _lab_id, p in (progress_map or {}).items():
        dt = _parse_iso_dt((p or {}).get("solved_at") or "")
        if dt:
            dates.add(dt.date())

    if not dates:
        return 0

    today = datetime.now().astimezone().date()
    streak = 0
    cur = today
    while cur in dates:
        streak += 1
        cur = cur - timedelta(days=1)
    return int(streak)
