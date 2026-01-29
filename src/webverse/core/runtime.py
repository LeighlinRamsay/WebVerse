from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any

RUNTIME = Path.home() / ".webverse" / "runtime.json"
RUNTIME.parent.mkdir(parents=True, exist_ok=True)

def get_runtime() -> Dict[str, Any]:
    if not RUNTIME.exists():
        return {"running_lab_id": None}
    try:
        return json.loads(RUNTIME.read_text(encoding="utf-8"))
    except Exception:
        return {"running_lab_id": None}

def set_running_lab(lab_id: Optional[str]) -> None:
    data = get_runtime()
    data["running_lab_id"] = lab_id
    RUNTIME.write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_running_lab() -> Optional[str]:
    return get_runtime().get("running_lab_id")
