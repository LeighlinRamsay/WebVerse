import os
import time
import pymysql
from flask import Flask, render_template, request, session, redirect, jsonify

app = Flask(
    __name__,
    static_folder="../Static",
    static_url_path="/Static",
    template_folder="../Templates"
)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-booth-key")

# Rate limiting store (per-IP, in-memory)
rate_limit_store = {}
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 1


def get_db():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "db"),
        user=os.environ.get("DB_USER", "rh_app"),
        password=os.environ.get("DB_PASSWORD", "rhAppS3cure2024"),
        database=os.environ.get("DB_NAME", "reelhouse_db"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


@app.route("/")
def index():
    if session.get("booth_auth"):
        return redirect("/dashboard")
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pin = request.form.get("pin", "")
        ip = request.remote_addr
        now = time.time()

        # Rate limiting
        attempts = rate_limit_store.get(ip, [])
        attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]

        if len(attempts) >= RATE_LIMIT_MAX:
            remaining = int(RATE_LIMIT_WINDOW - (now - attempts[0]))
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": max(remaining, 1)}), 429

        attempts.append(now)
        rate_limit_store[ip] = attempts

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT pin FROM equipment_pins WHERE active = 1")
        valid = cur.fetchone()
        db.close()

        if valid and pin == valid["pin"]:
            session["booth_auth"] = True
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid PIN")
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not session.get("booth_auth"):
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM equipment ORDER BY room_number")
    equipment = cur.fetchall()
    cur.execute("SELECT cl.*, e.name as equip_name FROM calibration_logs cl JOIN equipment e ON cl.equipment_id = e.id ORDER BY cl.logged_at DESC LIMIT 5")
    logs = cur.fetchall()
    db.close()
    return render_template("dashboard.html", equipment=equipment, logs=logs)


@app.route("/equipment/<int:equip_id>")
def equipment_detail(equip_id):
    if not session.get("booth_auth"):
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM equipment WHERE id = %s", (equip_id,))
    equip = cur.fetchone()
    if not equip:
        return "Not found", 404
    cur.execute("SELECT * FROM calibration_logs WHERE equipment_id = %s ORDER BY logged_at DESC", (equip_id,))
    logs = cur.fetchall()
    db.close()
    return render_template("equipment_detail.html", equip=equip, logs=logs)


@app.route("/calibration")
def calibration():
    if not session.get("booth_auth"):
        return redirect("/login")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT cl.*, e.name as equip_name FROM calibration_logs cl JOIN equipment e ON cl.equipment_id = e.id ORDER BY cl.logged_at DESC")
    logs = cur.fetchall()
    db.close()
    return render_template("calibration.html", logs=logs)


@app.route("/maintenance", methods=["GET", "POST"])
def maintenance():
    if not session.get("booth_auth"):
        return redirect("/login")
    submitted = False
    if request.method == "POST":
        submitted = True
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM equipment ORDER BY room_number")
    equipment = cur.fetchall()
    db.close()
    return render_template("maintenance.html", equipment=equipment, submitted=submitted)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=False)