# WebVerse

WebVerse is a local **web & API security lab runner**: a desktop app that discovers labs in `./labs/`, starts them with **Docker Compose**, opens them in your browser, and tracks your progress — all on your own machine.

> **Educational use only.** Labs are intentionally vulnerable. Do **not** expose them to the internet.

---

## Screenshot / Demo



<img width="1902" height="892" alt="home" src="https://github.com/user-attachments/assets/3a02f514-5bfd-4f6f-837b-3b60b693426e" />


<img width="1901" height="887" alt="lab" src="https://github.com/user-attachments/assets/2b490468-4919-43ef-afc4-bc69d6069d65" />


<img width="1897" height="902" alt="browse" src="https://github.com/user-attachments/assets/d3241724-2451-4f60-b5f6-240d0137ef77" />


<img width="1916" height="892" alt="progress new" src="https://github.com/user-attachments/assets/2c14bba5-d237-489c-84a4-6d84ef2f715e" />




---

## Why WebVerse?

Most practice environments are either:
- too heavy to set up,
- too scattered across repos,
- or too “manual” to run repeatedly.

WebVerse is built to make local practice **repeatable**:
- labs are self-contained
- starting/resetting takes one click
- you can iterate quickly, break things, reset, and try again

---

## Features

- 🧪 Browse included labs (name, difficulty, description, tags)
- ▶️ One-click **Start / Stop / Reset**
- 🌐 **Open in Browser** from the UI
- 🧾 View lab status and logs
- ✅ Track progress locally (`progress.db`)
- 🏁 Flag submission + verification (via `flag_sha256` in each `lab.yml`)

---

## Requirements

- **Linux or macOS**
- **Python 3.10+**
- **Docker** + **Docker Compose**
  - Linux: Docker Engine + Compose plugin
  - macOS: Docker Desktop

Install Python deps:

```bash
pip install -r requirements.txt
