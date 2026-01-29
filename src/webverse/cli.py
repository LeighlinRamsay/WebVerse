from __future__ import annotations

import errno
import os
import platform
import shutil
import socket
import subprocess
import sys

from webverse.gui.main import start

CAP_NET_BIND_SERVICE_BIT = 10  # cap_net_bind_service bit number


def _is_root() -> bool:
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0
    return False


def _username() -> str:
    # pwd is POSIX-only; import lazily
    try:
        import pwd  # type: ignore
        return pwd.getpwuid(os.geteuid()).pw_name  # type: ignore[attr-defined]
    except Exception:
        return os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"


def _user_groups() -> list[str]:
    # grp is POSIX-only; import lazily
    names: list[str] = []
    try:
        import grp  # type: ignore
        gids = set(os.getgroups())
        if hasattr(os, "getegid"):
            gids.add(os.getegid())
        for gid in sorted(gids):
            try:
                names.append(grp.getgrgid(gid).gr_name)  # type: ignore[attr-defined]
            except KeyError:
                pass
    except Exception:
        pass
    return sorted(set(names))


def _format_group_info() -> str:
    user = _username()
    groups = _user_groups()
    return f"User: {user}\nGroups: {', '.join(groups) if groups else '(unknown)'}\n"


def _process_has_cap_net_bind_service() -> bool:
    """
    Linux: check if current process has CAP_NET_BIND_SERVICE effective.
    Reads /proc/self/status -> CapEff.
    """
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("CapEff:"):
                    _, hexmask = line.split(":", 1)
                    mask = int(hexmask.strip(), 16)
                    return bool(mask & (1 << CAP_NET_BIND_SERVICE_BIT))
    except Exception:
        pass
    return False


def _python_binary_has_filecap() -> bool:
    """
    Linux: check whether sys.executable has cap_net_bind_service via file capabilities.
    Uses `getcap` if available.
    """
    getcap = shutil.which("getcap")
    if not getcap:
        return False
    try:
        r = subprocess.run([getcap, sys.executable], capture_output=True, text=True, check=False)
        out = (r.stdout or "").strip()
        return "cap_net_bind_service" in out
    except Exception:
        return False


def _linux_ip_unprivileged_port_start() -> int | None:
    """
    Linux: if this sysctl is <= 80, unprivileged users can bind to 80 without sudo/caps.
    /proc/sys/net/ipv4/ip_unprivileged_port_start
    """
    try:
        with open("/proc/sys/net/ipv4/ip_unprivileged_port_start", "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _can_bind_privileged_port_runtime() -> bool:
    """
    Best-effort runtime test: try to bind to a low port. We interpret:
    - success => you have permission
    - EACCES/EPERM => you do not
    - EADDRINUSE => try another
    """
    candidates = [1, 2, 7, 9, 11, 13, 19, 21, 23, 25, 81, 82]
    for port in candidates:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            return True
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EPERM):
                return False
            if e.errno == errno.EADDRINUSE:
                continue
            continue
        finally:
            try:
                s.close()
            except Exception:
                pass
    return False


def _linux_block_message() -> str:
    py = sys.executable
    group_info = _format_group_info()
    unpriv = _linux_ip_unprivileged_port_start()
    unpriv_str = f"{unpriv}" if unpriv is not None else "(unknown)"
    return (
        "\n"
        "WebVerse may need permission to bind to privileged ports (<1024), because some labs publish port 80.\n\n"
        + group_info +
        f"Linux sysctl net.ipv4.ip_unprivileged_port_start: {unpriv_str}\n\n"
        "Fix (recommended): grant CAP_NET_BIND_SERVICE to the exact Python you're running:\n"
        f"  sudo setcap 'cap_net_bind_service=+ep' '{py}'\n\n"
        "Alternative:\n"
        "  sudo webverse\n\n"
        "Or avoid privileged ports entirely:\n"
        "- Change any lab using host port 80 to a high port (8080+) in its docker-compose.yml\n\n"
    )


def _macos_block_message() -> str:
    group_info = _format_group_info()
    return (
        "\n"
        "WebVerse may need permission to bind to privileged ports (<1024), because some labs publish port 80.\n\n"
        + group_info +
        "\n"
        "Run with sudo:\n"
        "  sudo webverse\n\n"
        "Or avoid privileged ports:\n"
        "- Change labs that use host port 80 to a high port (8080+) in docker-compose.yml\n\n"
    )


def _linux_has_low_port_privilege() -> bool:
    if _is_root():
        return True
    if _process_has_cap_net_bind_service():
        return True
    if _python_binary_has_filecap():
        return True

    unpriv = _linux_ip_unprivileged_port_start()
    if unpriv is not None and unpriv <= 80:
        return True

    if _can_bind_privileged_port_runtime():
        return True

    return False


def main() -> int:
    system = platform.system().lower()

    if system == "linux":
        if not _linux_has_low_port_privilege():
            sys.stderr.write(_linux_block_message())
            return 1
        start()
        return 0

    if system == "darwin":
        if not _is_root():
            sys.stderr.write(_macos_block_message())
            return 1
        start()
        return 0

    # Other platforms: best-effort
    start()
    return 0
