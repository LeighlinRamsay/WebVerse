import os
from flask import Flask, render_template

app = Flask(__name__)

APP_DOMAIN = os.environ.get("APP_DOMAIN", "leaklore.local")
API_BASE = os.environ.get("API_BASE", "http://api.leaklore.local")
AUTH_USER_BASE = os.environ.get("AUTH_USER_BASE", "http://auth-user.leaklore.local")

@app.get("/")
def index():
    return render_template("index.html", app_domain=APP_DOMAIN, api_base=API_BASE)

@app.get("/track")
def track():
    return render_template("track.html", api_base=API_BASE)

# Hidden page (not linked in nav). Dirbust finds it.
@app.get("/login")
def login():
    return render_template("login.html", auth_user_base=AUTH_USER_BASE)

@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", auth_user_base=AUTH_USER_BASE)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
