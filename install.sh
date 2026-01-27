#!/usr/bin/env bash
set -euo pipefail

# Minimal WebVerse installer:
# - Installs Docker + Docker Compose (best effort)
# - Installs Python deps from requirements.txt into a venv

say()  { printf "\033[1;34m[+]\033[0m %s\n" "$*"; }
ok()   { printf "\033[1;32m[✓]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m[-]\033[0m %s\n" "$*"; exit 1; }

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

# Must run from repo root
[[ -f "requirements.txt" ]] || die "requirements.txt not found. Run this from the repo root."
[[ -f "webverse.py" ]] || warn "webverse.py not found in current dir (repo root recommended)."

install_docker_linux_apt() {
  say "Installing Docker + Compose (apt)..."
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl gnupg lsb-release

  # Prefer official Docker repo when possible
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/"$(. /etc/os-release; echo "$ID")"/gpg \
      | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
      $(. /etc/os-release; echo "$VERSION_CODENAME") stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null || true
  fi

  sudo apt-get update -y

  # Install engine + compose plugin
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
    || sudo apt-get install -y docker.io docker-compose-plugin \
    || sudo apt-get install -y docker.io docker-compose

  # Enable docker service if available
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now docker || true
  elif command -v service >/dev/null 2>&1; then
    sudo service docker start || true
  fi

  # Add user to docker group (optional but nice)
  if getent group docker >/dev/null 2>&1; then
    sudo usermod -aG docker "$USER" || true
    warn "Added $USER to docker group (if possible). Log out/in (or reboot) for it to take effect."
  fi
}

install_docker_linux_dnf() {
  say "Installing Docker + Compose (dnf)..."
  sudo dnf -y install dnf-plugins-core || true
  sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo || true
  sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
    || sudo dnf -y install docker docker-compose || true
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now docker || true
  fi
  sudo usermod -aG docker "$USER" || true
  warn "Added $USER to docker group (if possible). Log out/in (or reboot) for it to take effect."
}

install_docker_linux_pacman() {
  say "Installing Docker + Compose (pacman)..."
  sudo pacman -Sy --noconfirm docker docker-compose || true
  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now docker || true
  fi
  sudo usermod -aG docker "$USER" || true
  warn "Added $USER to docker group (if possible). Log out/in (or reboot) for it to take effect."
}

install_docker_macos() {
  # Reality: you need Docker Desktop (or an alternative daemon) for Docker to actually run on macOS.
  # We'll best-effort install the CLI via Homebrew if available, but still tell them to install Desktop.
  if command -v docker >/dev/null 2>&1; then
    ok "docker is already installed."
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    say "Installing Docker CLI + Docker Compose via Homebrew..."
    brew install docker docker-compose || true
    warn "You still need a Docker daemon on macOS (usually Docker Desktop)."
    warn "Install Docker Desktop, then re-run WebVerse."
  else
    warn "Homebrew not found and Docker isn't installed."
    warn "Install Docker Desktop for macOS, then re-run this script."
  fi
}

ensure_docker_available() {
  if command -v docker >/dev/null 2>&1; then
    ok "docker command found."
  else
    warn "docker command not found."
    if [[ "$OS" == "linux" ]]; then
      if command -v apt-get >/dev/null 2>&1; then
        install_docker_linux_apt
      elif command -v dnf >/dev/null 2>&1; then
        install_docker_linux_dnf
      elif command -v pacman >/dev/null 2>&1; then
        install_docker_linux_pacman
      else
        die "Unsupported Linux package manager. Install Docker + Docker Compose manually."
      fi
    elif [[ "$OS" == "darwin" ]]; then
      install_docker_macos
    else
      die "Unsupported OS: $OS"
    fi
  fi

  # Compose check (plugin or legacy)
  if docker compose version >/dev/null 2>&1; then
    ok "Docker Compose plugin available."
  elif command -v docker-compose >/dev/null 2>&1; then
    ok "docker-compose available."
  else
    warn "Docker Compose not found. Attempting to install..."
    if [[ "$OS" == "linux" ]]; then
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y docker-compose-plugin docker-compose || true
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf -y install docker-compose-plugin docker-compose || true
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm docker-compose || true
      fi
    elif [[ "$OS" == "darwin" ]]; then
      if command -v brew >/dev/null 2>&1; then
        brew install docker-compose || true
      fi
    fi
  fi

  # Docker daemon sanity (won't succeed on macOS without Desktop running)
  if docker info >/dev/null 2>&1; then
    ok "Docker daemon reachable."
  else
    warn "Docker daemon not reachable as this user right now."
    if [[ "$OS" == "linux" ]]; then
      warn "Try: sudo systemctl start docker  (or log out/in if you were added to the docker group)."
    else
      warn "On macOS: start Docker Desktop (or another Docker daemon)."
    fi
  fi
}

install_python_deps() {
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.10+."

  say "Creating venv (.venv) if missing..."
  if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
  fi

  say "Installing Python deps from requirements.txt..."
  .venv/bin/python -m pip install --upgrade pip setuptools wheel
  .venv/bin/pip install -r requirements.txt

  ok "Python deps installed into .venv"
}

say "Starting install..."
ensure_docker_available
install_python_deps

echo ""
ok "Done."
echo "Run:"
echo "  source .venv/bin/activate"
echo "  python3 webverse.py"
echo ""
warn "If Docker permissions fail on Linux, log out/in (docker group) or run Docker commands with sudo."
warn "On macOS, Docker requires Docker Desktop (or another daemon) to actually run containers."
