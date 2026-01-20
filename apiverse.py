#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import os
import subprocess
import sqlite3
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # pip install pyyaml
except ImportError:
    print("Missing dependency: pyyaml. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent
LABS_DIR = ROOT / "labs"
DIFFICULTIES = ("easy", "medium", "hard", "master")

STATE_DIR = Path.home() / ".apiverse"
DB_PATH = STATE_DIR / "apiverse.db"

# ------------------ TERMINAL COLORS ------------------------

ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_RED = "\033[31m"
ANSI_PURPLE = "\033[35m"

DIFF_COLOR = {
    "easy": ANSI_GREEN,
    "medium": ANSI_YELLOW,
    "hard": ANSI_RED,
    "master": ANSI_PURPLE,
}

def supports_color() -> bool:
    # Basic, portable check. Disable colors when piped or when NO_COLOR is set.
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()

def colorize_name(name: str, difficulty: str) -> str:
    if not supports_color():
        return name
    c = DIFF_COLOR.get(difficulty, "")
    return f"{c}{name}{ANSI_RESET}" if c else name


@dataclass(frozen=True)
class Lab:
    id: str
    name: str
    difficulty: str
    description: str
    dir: Path
    compose_file: Path
    entrypoint_url: Optional[str]
    flag_sha256: Optional[str]


# ------------------ HELPER FUNCTIONS ------------------------

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def db_connect() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS progress (
            lab_id TEXT PRIMARY KEY,
            started_at TEXT,
            solved_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT
        )
        """
    )
    return conn


def db_mark_started(conn: sqlite3.Connection, lab_id: str) -> None:
    conn.execute(
        """
        INSERT INTO progress (lab_id, started_at, attempts)
        VALUES (?, ?, 0)
        ON CONFLICT(lab_id) DO UPDATE SET
            started_at = COALESCE(progress.started_at, excluded.started_at)
        """,
        (lab_id, now_utc_iso()),
    )
    conn.commit()


def db_record_attempt(conn: sqlite3.Connection, lab_id: str) -> None:
    conn.execute(
        """
        INSERT INTO progress (lab_id, started_at, attempts, last_attempt_at)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(lab_id) DO UPDATE SET
            attempts = progress.attempts + 1,
            last_attempt_at = excluded.last_attempt_at,
            started_at = COALESCE(progress.started_at, excluded.started_at)
        """,
        (lab_id, now_utc_iso(), now_utc_iso()),
    )
    conn.commit()


def db_mark_solved(conn: sqlite3.Connection, lab_id: str) -> None:
    conn.execute(
        """
        UPDATE progress
        SET solved_at = COALESCE(solved_at, ?)
        WHERE lab_id = ?
        """,
        (now_utc_iso(), lab_id),
    )
    conn.commit()


def db_solved_set(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT lab_id FROM progress WHERE solved_at IS NOT NULL"
    ).fetchall()
    return {r[0] for r in rows}




def run(cmd: List[str], *, cwd: Optional[Path] = None, verbose: bool = True) -> int:
    """
    Runs a command.

    - verbose=True: stream output to terminal (default behavior)
    - verbose=False: suppress output unless the command fails, then print captured output
    """
    try:
        if verbose:
            proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
            return proc.returncode

        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode != 0 and proc.stdout:
            print(proc.stdout, file=sys.stderr)
        return proc.returncode

    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}", file=sys.stderr)
        return 127

def run_capture(cmd: List[str], *, cwd: Optional[Path] = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"


def _quiet_rc(cmd: List[str]) -> int:
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc.returncode
    except FileNotFoundError:
        return 127


def docker_compose_cmd() -> List[str]:
    # Prefer Docker Compose v2: `docker compose`
    if _quiet_rc(["docker", "compose", "version"]) == 0:
        return ["docker", "compose"]
    # Fallback: `docker-compose`
    if _quiet_rc(["docker-compose", "version"]) == 0:
        return ["docker-compose"]

    print("Docker Compose not found. Install Docker Desktop or docker-compose.", file=sys.stderr)
    sys.exit(2)

def get_running_labs(labs: Dict[str, Lab]) -> List[Lab]:
    """
    Returns a list of running APIverse labs by inspecting docker container labels.
    Uses the compose project label: com.docker.compose.project
    """
    # Requires docker CLI, but you already depend on docker for compose.
    rc, out, err = run_capture([
        "docker", "ps",
        "--filter", "label=com.docker.compose.project",
        "--format", '{{.Label "com.docker.compose.project"}}'
    ])

    if rc != 0:
        # If docker isn't available, treat as "unknown / none"
        return []

    projects = {line.strip() for line in out.splitlines() if line.strip()}
    running: List[Lab] = []
    for lab in labs.values():
        if project_name(lab.id) in projects:
            running.append(lab)

    running.sort(key=lambda x: x.id)
    return running


def load_lab_manifest(lab_dir: Path) -> Optional[Lab]:
    manifest = lab_dir / "lab.yml"
    if not manifest.exists():
        return None

    with manifest.open("r", encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    lab_id = str(data.get("id", lab_dir.name)).strip()
    name = str(data.get("name", lab_id)).strip()
    difficulty = str(data.get("difficulty", "")).strip().lower()
    description = str(data.get("description", "")).strip()

    if difficulty not in DIFFICULTIES:
        print(f"[WARN] Lab '{lab_dir.name}' has invalid difficulty: '{difficulty}'", file=sys.stderr)
        return None

    compose_rel = str(data.get("compose_file", "docker-compose.yml"))
    compose_file = (lab_dir / compose_rel).resolve()
    if not compose_file.exists():
        print(f"[WARN] Lab '{lab_id}' missing compose file: {compose_file}", file=sys.stderr)
        return None

    entrypoint_url = None
    ep = data.get("entrypoint") or {}
    if isinstance(ep, dict):
        entrypoint_url = ep.get("base_url")

    flag_sha256 = None
    raw_hash = data.get("flag_sha256")
    if isinstance(raw_hash, str) and raw_hash.strip():
        flag_sha256 = raw_hash.strip().lower()

    return Lab(
        id=lab_id,
        name=name,
        difficulty=difficulty,
        description=description,
        dir=lab_dir,
        compose_file=compose_file,
        entrypoint_url=entrypoint_url,
        flag_sha256=flag_sha256,
    )


def discover_labs() -> Dict[str, Lab]:
    labs: Dict[str, Lab] = {}
    if not LABS_DIR.exists():
        return labs

    for p in LABS_DIR.iterdir():
        if p.is_dir():
            lab = load_lab_manifest(p)
            if lab:
                labs[lab.id] = lab
    return labs


def project_name(lab_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in lab_id)
    return f"apiverse_{safe}"


def cmd_list(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    wanted: Optional[str] = None
    if args.easy:
        wanted = "easy"
    elif args.medium:
        wanted = "medium"
    elif args.hard:
        wanted = "hard"
    elif args.master:
        wanted = "master"
    elif args.all:
        wanted = None

    conn = db_connect()
    solved = db_solved_set(conn)

    groups: Dict[str, List[Lab]] = {d: [] for d in DIFFICULTIES}
    for lab in labs.values():
        groups[lab.difficulty].append(lab)
    for d in DIFFICULTIES:
        groups[d].sort(key=lambda x: x.id)

    def print_lab(l: Lab) -> None:
        mark = "✓" if l.id in solved else " "
        colored_name = colorize_name(l.name, l.difficulty)
        print(f"  {mark} {l.id}: {colored_name}")

    if wanted:
        print(f"{wanted.upper()} labs:")
        for l in groups[wanted]:
            print_lab(l)
        return 0

    # Default: list all, but only show difficulties that actually have labs
    for d in DIFFICULTIES:
        if not groups[d]:
            continue
        print(f"{d.upper()} labs:")
        for l in groups[d]:
            print_lab(l)
        print()

    # If literally no labs exist (or all were invalid), tell the user
    if all(len(groups[d]) == 0 for d in DIFFICULTIES):
        print("No labs found in ./labs/")

    return 0

def cmd_submit(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    lab = labs.get(args.lab_id)
    if not lab:
        print(f"Unknown lab '{args.lab_id}'. Try: python3 apiverse.py list", file=sys.stderr)
        return 2

    if not lab.flag_sha256:
        print(f"Lab '{lab.id}' has no flag_sha256 in lab.yml", file=sys.stderr)
        return 2

    conn = db_connect()
    db_mark_started(conn, lab.id)
    db_record_attempt(conn, lab.id)

    submitted_hash = sha256_hex(args.flag.strip())
    if submitted_hash == lab.flag_sha256:
        db_mark_solved(conn, lab.id)
        print(f"🏁 Correct! Lab solved: {lab.id}")
        return 0

    print("❌ Incorrect flag.")
    return 1

def cmd_progress(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    conn = db_connect()
    solved = db_solved_set(conn)

    total = len(labs)
    solved_count = sum(1 for lab_id in labs.keys() if lab_id in solved)

    bar_len = 30
    pct = 0 if total == 0 else solved_count / total
    filled = int(round(pct * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)

    print(f"Progress: [{bar}] {solved_count}/{total} ({int(pct*100)}%)")
    return 0

def cmd_info(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    lab = labs.get(args.lab_id)
    if not lab:
        print(f"Unknown lab '{args.lab_id}'. Try: python3 apiverse.py list", file=sys.stderr)
        return 2

    print(lab.description or "(No description set in lab.yml)")
    return 0

def cmd_status(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    running = get_running_labs(labs)

    if not running:
        print("No lab is currently running.")
        return 0

    # You want to limit to one lab, but if multiple exist, show them anyway.
    if len(running) > 1:
        print("⚠ Multiple labs appear to be running (APIverse expects only one):")

    for lab in running:
        print(f"{lab.id}: {lab.name}")
        print(f"Difficulty: {lab.difficulty}")
        print(f"Description: {lab.description}")
        print()

    return 0

def cmd_play(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    lab = labs.get(args.lab_id)
    if not lab:
        print(f"Unknown lab '{args.lab_id}'. Try: python3 apiverse.py list", file=sys.stderr)
        return 2

    # Enforce: only one lab running at a time
    running = get_running_labs(labs)
    if running:
        # If the same lab is already running, just remind the user
        if len(running) == 1 and running[0].id == lab.id:
            print(f"✅ Already running: {lab.id} ({lab.difficulty})")
            if lab.entrypoint_url:
                print(f"Entrypoint: {lab.entrypoint_url}")
            return 0

        # Otherwise block and tell them what’s running
        current = running[0]
        print("❌ Another lab is already running. Stop it first with:")
        print(f"   python3 apiverse.py down {current.id}")
        print("\nCurrently running:")
        print(f"  {current.id}: {current.name} ({current.difficulty}) - {current.description}")
        return 2

    # Mark started for “game” tracking
    conn = db_connect()
    db_mark_started(conn, lab.id)

    compose = docker_compose_cmd()
    proj = project_name(lab.id)

    cmd = compose + ["-p", proj, "-f", str(lab.compose_file), "up", "-d", "--remove-orphans"]
    if args.no_build is False:
        cmd.append("--build")

    rc = run(cmd, cwd=lab.dir, verbose=args.verbose)
    if rc == 0:
        print(f"\n🎮 Playing: {lab.id} ({lab.difficulty})")
        if lab.entrypoint_url:
            print(f"Entrypoint: {lab.entrypoint_url}")
        print(f"Project: {proj}")
    return rc


def cmd_down(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    lab = labs.get(args.lab_id)
    if not lab:
        print(f"Unknown lab '{args.lab_id}'. Try: python3 apiverse.py list", file=sys.stderr)
        return 2

    compose = docker_compose_cmd()
    proj = project_name(lab.id)

    # Always remove volumes for a clean teardown (your requirement)
    cmd = compose + ["-p", proj, "-f", str(lab.compose_file), "down", "-v", "--remove-orphans"]
    rc = run(cmd, cwd=lab.dir, verbose=args.verbose)
    if rc == 0:
        print(f"🧹 Down: {lab.id} (volumes removed)")
    return rc

def cmd_reset(labs: Dict[str, Lab], args: argparse.Namespace) -> int:
    lab = labs.get(args.lab_id)
    if not lab:
        print(f"Unknown lab '{args.lab_id}'. Try: python3 apiverse.py list", file=sys.stderr)
        return 2

    # If another lab is running, don't implicitly kill it
    running = get_running_labs(labs)
    if running and not (len(running) == 1 and running[0].id == lab.id):
        current = running[0]
        print("❌ A different lab is running. Stop it first with:")
        print(f"   python3 apiverse.py down {current.id}")
        print("\nCurrently running:")
        print(f"  {current.id}: {current.name} ({current.difficulty}) - {current.description}")
        return 2

    # Down this lab (removes volumes)
    rc = cmd_down(labs, argparse.Namespace(lab_id=lab.id, verbose=args.verbose))
    if rc != 0:
        return rc

    # Then play it again (fresh)
    play_args = argparse.Namespace(lab_id=lab.id, no_build=args.no_build, verbose=args.verbose)
    return cmd_play(labs, play_args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apiverse.py")
    sub = p.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Start playing a lab (only one lab can run at a time)")
    play.add_argument("lab_id")
    play.add_argument("--no-build", action="store_true", help="Skip docker image build")
    play.add_argument("-v", "--verbose", action="store_true", help="Show docker compose output")
    play.set_defaults(_fn=cmd_play, no_build=False)

    info = sub.add_parser("info", help="Show a lab's description")
    info.add_argument("lab_id")
    info.set_defaults(_fn=cmd_info)

    reset = sub.add_parser("reset", help="Reset a lab (down -v then play)")
    reset.add_argument("lab_id")
    reset.add_argument("--no-build", action="store_true", help="Skip docker image build")
    reset.add_argument("-v", "--verbose", action="store_true", help="Show docker compose output")
    reset.set_defaults(_fn=cmd_reset, no_build=False)

    status = sub.add_parser("status", help="Show which lab is currently running")
    status.set_defaults(_fn=cmd_status)

    down = sub.add_parser("down", help="Stop a lab (always removes volumes)")
    down.add_argument("lab_id")
    down.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show docker compose output (otherwise suppressed)"
    )
    down.set_defaults(_fn=cmd_down)

    lst = sub.add_parser("list", help="List available labs")
    g = lst.add_mutually_exclusive_group()
    g.add_argument("--easy", action="store_true")
    g.add_argument("--medium", action="store_true")
    g.add_argument("--hard", action="store_true")
    g.add_argument("--master", action="store_true")
    g.add_argument("--all", action="store_true")
    lst.set_defaults(_fn=cmd_list)

    submit = sub.add_parser("submit", help="Submit a flag for a lab")
    submit.add_argument("lab_id")
    submit.add_argument("flag")
    submit.set_defaults(_fn=cmd_submit)

    prog = sub.add_parser("progress", help="Show overall progress")
    prog.set_defaults(_fn=cmd_progress)

    return p


def main() -> int:
    labs = discover_labs()
    parser = build_parser()
    args = parser.parse_args()

    if not labs and args.command == "list":
        print("No labs found in ./labs/")
        return 0

    return args._fn(labs, args)


if __name__ == "__main__":
    raise SystemExit(main())