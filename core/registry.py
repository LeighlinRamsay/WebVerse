from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict, List

from .models import Lab

LABS_DIR = Path("labs")

def _safe_str(x: Any, default: str = "") -> str:
    return str(x).strip() if x is not None else default

def discover_labs(labs_dir: Path = LABS_DIR) -> List[Lab]:
    """Discover labs from ./labs/*/lab.yml.

    Each lab folder must include:
      - lab.yml
      - docker-compose.yml (or compose_file specified in lab.yml)

    lab.yml schema (minimal):
      id: <slug>
      name: <display name>
      difficulty: easy|medium|hard|insane
      description: <text>
      compose_file: docker-compose.yml
      entrypoint:
        base_url: http://something.local/
      flag_sha256: <sha256 of the flag string (strip whitespace)>
    """
    labs: List[Lab] = []
    if not labs_dir.exists():
        return labs

    for lab_dir in sorted(labs_dir.iterdir()):
        if not lab_dir.is_dir():
            continue

        manifest = lab_dir / "lab.yml"
        if not manifest.exists():
            continue

        data: Dict[str, Any] = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        entry = data.get("entrypoint") or {}
        if not isinstance(entry, dict):
            entry = {"value": entry}

        labs.append(Lab(
            id=_safe_str(data.get("id"), lab_dir.name),
            name=_safe_str(data.get("name"), lab_dir.name),
            description=_safe_str(data.get("description"), ""),
            difficulty=_safe_str(data.get("difficulty"), "unknown").lower(),
            compose_file=_safe_str(data.get("compose_file"), "docker-compose.yml"),
            entrypoint=entry,
            flag_sha256=_safe_str(data.get("flag_sha256"), ""),
            path=lab_dir
        ))
    return labs
