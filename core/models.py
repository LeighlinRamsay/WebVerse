from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class Lab:
    id: str
    name: str
    description: str
    difficulty: str
    path: Path

    # docker-compose.yml file name (relative to lab path)
    compose_file: str = "docker-compose.yml"

    # Entry info from lab.yml (typically contains base_url, etc.)
    entrypoint: Dict[str, Any] = None

    # sha256 of the exact flag string (after stripping whitespace)
    flag_sha256: str = ""

    def base_url(self) -> Optional[str]:
        if isinstance(self.entrypoint, dict):
            v = self.entrypoint.get("base_url")
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
