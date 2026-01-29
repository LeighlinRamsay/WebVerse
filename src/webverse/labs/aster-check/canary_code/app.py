from flask import Flask, render_template, abort

app = Flask(__name__)

# Minimal “gitea-like” browsing.
# The key leak is in an older commit of fetcher source.
REPO_NAME = "fetch-gateway"

COMMITS = [
    {
        "sha": "a1f3c9e",
        "title": "initial: hardcode signing key for ops bring-up",
        "files": {
            "fetcher/app.py": """import os
import hmac
import hashlib

# TODO: move to env before production
SIGNING_KEY = "WEBVERSE{51GN3D_URL5_D0N7_H1D3_53CR375}"

def sign(url: str) -> str:
    return hmac.new(SIGNING_KEY.encode(), url.encode(), hashlib.sha256).hexdigest()
"""
        }
    },
    {
        "sha": "c0de7a2",
        "title": "fix: redact key from repo, load from env",
        "files": {
            "fetcher/app.py": """import os
import hmac
import hashlib

# moved out of repo
SIGNING_KEY = os.environ.get("SIGNING_KEY", "REDACTED")

def sign(url: str) -> str:
    return hmac.new(SIGNING_KEY.encode(), url.encode(), hashlib.sha256).hexdigest()
"""
        }
    }
]

@app.get("/")
def home():
    return render_template("home.html", repo=REPO_NAME)

@app.get("/repo/<name>")
def repo(name):
    if name != REPO_NAME:
        abort(404)
    return render_template("repo.html", repo=REPO_NAME, commits=COMMITS)

@app.get("/repo/<name>/commit/<sha>")
def commit(name, sha):
    if name != REPO_NAME:
        abort(404)
    c = next((x for x in COMMITS if x["sha"] == sha), None)
    if not c:
        abort(404)
    return render_template("commit.html", repo=REPO_NAME, commit=c)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
