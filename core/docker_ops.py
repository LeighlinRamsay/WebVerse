from __future__ import annotations

import subprocess
from typing import Optional, Tuple, List

def _run(cmd: List[str], cwd: Optional[str] = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def docker_available() -> Tuple[bool, str]:
    """Return (ok, version_or_reason). If ok=True, second value is the Docker Server version string."""
    try:
        p = _run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=8)
        if p.returncode == 0 and p.stdout.strip():
            return True, p.stdout.strip()

        # fallback: try plain docker version and just say "Installed" if it works
        p2 = _run(["docker", "version"], timeout=8)
        if p2.returncode == 0:
            return True, "Installed"

        return False, (p.stderr or p.stdout or "Docker not available").strip()
    except FileNotFoundError:
        return False, "Docker CLI not found"
    except Exception as e:
        return False, str(e)

def compose_v2_available() -> Tuple[bool, str]:
    """
    Require Docker Compose v2 (the `docker compose` plugin).
    Return (ok, version_or_reason).
    """
    try:
        p = _run(["docker", "compose", "version", "--short"], timeout=8)
        if p.returncode == 0 and p.stdout.strip():
            return True, p.stdout.strip()

        # Some builds don't support --short; fall back to full output
        p2 = _run(["docker", "compose", "version"], timeout=8)
        if p2.returncode == 0 and (p2.stdout.strip() or p2.stderr.strip()):
            out = (p2.stdout or p2.stderr or "").strip()
            return True, out.splitlines()[0] if out else "Installed"

        return False, (p.stderr or p.stdout or "docker compose not available").strip()
    except FileNotFoundError:
        return False, "Docker CLI not found"
    except Exception as e:
        return False, str(e)


def compose_has_running(lab_path: str, compose_file: str = "docker-compose.yml") -> Tuple[bool, str]:
    """
    Return (running, details). Uses Compose v2 filtering to avoid fragile parsing.
    """
    try:
        p = _run(
            ["docker", "compose", "-f", compose_file, "ps", "--status", "running", "-q"],
            cwd=lab_path,
            timeout=30,
        )
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "compose ps failed").strip()
        return (bool(p.stdout.strip()), p.stdout.strip())
    except Exception as e:
        return False, str(e)


def compose_reset(lab_path: str, compose_file: str = "docker-compose.yml") -> subprocess.CompletedProcess:
    down = _run(["docker", "compose", "-f", compose_file, "down", "-v"], cwd=lab_path, timeout=600)
    up = _run(["docker", "compose", "-f", compose_file, "up", "-d", "--build"], cwd=lab_path, timeout=600)

    combined_stdout = (down.stdout or "")
    if combined_stdout and not combined_stdout.endswith("\n"):
        combined_stdout += "\n"
    combined_stdout += (up.stdout or "")

    combined_stderr = (down.stderr or "")
    if combined_stderr and not combined_stderr.endswith("\n"):
        combined_stderr += "\n"
    combined_stderr += (up.stderr or "")

    # ✅ Success should reflect the final state ("up")
    rc = up.returncode

    return subprocess.CompletedProcess(
        args=["docker", "compose", "-f", compose_file, "reset"],
        returncode=rc,
        stdout=combined_stdout,
        stderr=combined_stderr,
    )

def compose_up(lab_path: str, compose_file: str = "docker-compose.yml") -> subprocess.CompletedProcess:
    return _run(["docker", "compose", "-f", compose_file, "up", "-d", "--build"], cwd=lab_path, timeout=600)

def compose_down(lab_path: str, compose_file: str = "docker-compose.yml") -> subprocess.CompletedProcess:
    return _run(["docker", "compose", "-f", compose_file, "down", "-v"], cwd=lab_path, timeout=600)

def compose_ps(lab_path: str, compose_file: str = "docker-compose.yml") -> subprocess.CompletedProcess:
    # Keep it simple/portable: parse stdout in GUI if needed
    return _run(["docker", "compose", "-f", compose_file, "ps"], cwd=lab_path, timeout=30)

def compose_logs(lab_path: str, compose_file: str = "docker-compose.yml", tail: int = 200) -> subprocess.CompletedProcess:
    return _run(["docker", "compose", "-f", compose_file, "logs", "--no-color", "--tail", str(tail)], cwd=lab_path, timeout=30)

def compose_restart(lab_path: str, compose_file: str = "docker-compose.yml") -> subprocess.CompletedProcess:
    return _run(["docker", "compose", "-f", compose_file, "restart"], cwd=lab_path, timeout=120)
