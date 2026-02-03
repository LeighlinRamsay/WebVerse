# WebVerse

WebVerse is a local **web & API security lab runner** — a desktop app that discovers labs, starts them with **Docker Compose**, opens them in your browser, and tracks progress on your machine.

> **Educational use only.** Labs are intentionally vulnerable. **Do not expose them to the internet.**

---

### Install WebVerse from GitHub
```bash
pipx install git+https://github.com/LeighlinRamsay/WebVerse.git
```

---

## Screenshot / Demo]

<img width="1916" height="885" alt="HOME UPDATED" src="https://github.com/user-attachments/assets/9191393e-de4c-4d87-8945-04d4d05ec87d" />

<img width="1911" height="882" alt="PIXEL" src="https://github.com/user-attachments/assets/5ea6d593-030f-4342-af0f-d707f0c4352c" />

<img width="1916" height="890" alt="BROWSE LABS UPDATED" src="https://github.com/user-attachments/assets/cb82b786-01e4-4eee-95b0-1a7f928507c8" />

<img width="1910" height="896" alt="PROGRESS UPDATED" src="https://github.com/user-attachments/assets/f030ac78-1135-49d3-969d-6dc6ddf624b4" />

---

## Install (Recommended): pipx

`pipx` installs WebVerse into an isolated environment and exposes a `webverse` command.

### 0) Requirements
- **Linux** or **macOS**
- **Python 3.10+**
- **Docker** + **Docker Compose v2** (must support `docker compose`)

Quick check:

```bash
python3 --version
docker --version
docker compose version
```

> If `docker compose version` fails, install Docker Desktop (macOS) or Docker Engine + Compose plugin (Linux).

### 1) Install pipx (one time)

**Debian/Kali/Ubuntu:**
```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
```

Restart your terminal (or run `source ~/.bashrc` / `source ~/.zshrc`).

### 2) Install WebVerse from GitHub
```bash
pipx install git+https://github.com/LeighlinRamsay/WebVerse.git
```

### 3) Run WebVerse
```bash
webverse
```

### Update / uninstall
```bash
pipx upgrade webverse
pipx uninstall webverse
```

---

## Install (Alternative): Run from source (developer mode)

Use this if you’re editing the code or building labs.

### 1) Clone
```bash
git clone https://github.com/LeighlinRamsay/WebVerse.git
cd WebVerse
```

### 2) Create a venv + install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Run
```bash
python3 webverse.py
```

---

## Features

- 🧪 Browse included labs (difficulty, tags, description)
- ▶️ One-click **Start / Stop / Reset**
- 🌐 **Open in Browser** from the UI
- 🧾 View lab status and logs
- ✅ Track progress locally (`progress.db`)
- 🏁 Flag submission + verification (via `flag_sha256` in each `lab.yml`)

---

## Using WebVerse

1. Open WebVerse
2. Go to **Labs** and pick a lab
3. Click **Start** (Docker Compose spins up the lab)
4. Click **Open in Browser**
5. When you capture the flag, submit it in the lab page to mark it solved
6. Use **Reset** to restore the lab and try again

### Where are labs stored?
By default, labs live in:
- `./labs/` (in a source checkout)

---

## Troubleshooting

### Docker permission denied (Linux)
If Docker works only with `sudo`, add your user to the docker group:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker ps
```

### Port 80 / privileged ports (Linux/macOS)
Some labs bind to low ports. If a lab fails to start with permission errors:
- Update the lab’s `docker-compose.yml` to use a higher port (e.g. `8080:80`), or
- Run WebVerse with elevated permissions (not recommended as default)

### Lab won’t start / stuck starting
- Confirm Docker is running: `docker ps`
- Check the lab logs in the WebVerse UI
- Try **Stop → Reset → Start**

---

## Why WebVerse?

Most practice environments are either:
- heavy to set up,
- scattered across repos,
- or too manual to run repeatedly.

WebVerse makes local practice **repeatable**:
- labs are self-contained
- starting/resetting takes one click
- you can iterate quickly, break things, reset, and try again

---

## Disclaimer

WebVerse and included labs are for **education and authorized testing only**.
You are responsible for how you use this software.
