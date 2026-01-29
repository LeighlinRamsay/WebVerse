import subprocess
from flask import Flask, request, session, redirect, render_template, jsonify

app = Flask(__name__)
app.secret_key = "leak-lore-prod-handler-secret"

OPS_USER = "opsadmin"
OPS_PASS = "ProdHandler!2026"

BLACKLIST = [";", "|", "&"]

BLACK_CHARS = [",", ";", "&", "|", ">", "<"]
ALLOWED_KEYWORDS = ["ls", "ps", "ip", "mem", "uname", "free", "whoami"]

def validate_cmd(cmd: str):
    if not isinstance(cmd, str):
        return False, "Missing command"
    raw = cmd
    cmd = cmd.strip()
    if not cmd:
        return False, "Missing command"

    lowered = cmd.lower()

    # Block ALL whitespace (spaces, tabs, newlines)
    if any(ch.isspace() for ch in lowered):
        return False, "Spaces are not allowed"

    # Block forbidden characters
    for bad in BLACK_CHARS:
        if bad in lowered:
            return False, "Blocked characters detected"

    # Block forbidden word
    if "cat" in lowered:
        return False, "Blocked keyword detected"

    # Must contain at least one allowed keyword
    if not any(k in lowered for k in ALLOWED_KEYWORDS):
        return False, "Command not allowed"

    return True, cmd

@app.get("/")
def home():
    if session.get("authed"):
        return redirect("/panel")
    return redirect("/login")

@app.get("/login")
def login_page():
    return render_template("login.html")

@app.post("/login")
def do_login():
    u = request.form.get("username", "")
    p = request.form.get("password", "")
    if u == OPS_USER and p == OPS_PASS:
        session["authed"] = True
        return redirect("/panel")
    return render_template("login.html", error="Invalid credentials"), 401

@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.get("/panel")
def panel():
    if not session.get("authed"):
        return redirect("/login")
    return render_template("panel.html")

# INTENTIONALLY VULNERABLE:
# - naive blacklist for ; | &
# - shell=True execution of user-influenced string
@app.post("/api/v2/command")
def command_new():
    if not session.get("authed"):
        return jsonify({"error": "Unauthorized"}), 401

    cmd = (request.json or {}).get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        return jsonify({"error": "Missing command"}), 400

    for bad in BLACKLIST:
        if bad in cmd:
            return jsonify({"error": "Blocked characters detected"}), 400

    try:
        full = f"/usr/local/bin/syscheck {cmd}"
        out = subprocess.check_output(full, shell=True, stderr=subprocess.STDOUT, text=True, timeout=3)
        return jsonify({"ok": True, "output": out})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "output": e.output}), 200
    except Exception as e:
        return jsonify({"ok": False, "output": str(e)}), 200

@app.post("/api/v1/command")
def command():
    if not session.get("authed"):
        return jsonify({"error": "Unauthorized"}), 401

    cmd = (request.json or {}).get("command", "")

    ok, res = validate_cmd(cmd)
    if not ok:
        return jsonify({"error": res}), 400

    cmd = res
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=3)
        return jsonify({"ok": True, "output": out})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "output": e.output}), 200
    except Exception as e:
        return jsonify({"ok": False, "output": str(e)}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
