from __future__ import annotations

from typing import Optional

# Keep XP values consistent across the app (Browse Labs  Progress)
# Values match the existing Progress page tuning.
DIFF_XP = {
    "easy": 50,
    "medium": 120,
    "hard": 250,
    "master": 450,
}


def _norm(diff: Optional[str]) -> str:
    return (diff or "").strip().lower()


def base_xp_for_difficulty(diff: Optional[str]) -> int:
    return DIFF_XP.get(_norm(diff), 0)


def attempt_bonus(attempts: int) -> int:
    """Attempt bonus used by Progress page (same behavior as before)."""
    if attempts <= 1:
        return 50
    if attempts <= 3:
        return 25
    return 0
