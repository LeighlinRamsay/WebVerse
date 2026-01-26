# core/flags.py
from __future__ import annotations
import hashlib

def sha256_hex(s: str) -> str:
    # IMPORTANT: hash the exact string the player submits (after strip)
    b = (s or "").encode("utf-8")
    return hashlib.sha256(b).hexdigest()

def flag_matches_sha256(submitted_flag: str, expected_sha256: str) -> bool:
    if not submitted_flag or not expected_sha256:
        return False
    submitted = (submitted_flag or "").strip()
    exp = (expected_sha256 or "").strip().lower()
    if not submitted or not exp:
        return False
    return sha256_hex(submitted) == exp
