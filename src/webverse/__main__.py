from __future__ import annotations

from webverse.cli import main
from webverse.core.usercounter import send_event

send_event("app_started")

raise SystemExit(main())
