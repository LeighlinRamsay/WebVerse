import os
import secrets
from flask import Flask, jsonify, request, make_response

app = Flask(__name__)

# "unguessable" secret UA value
# - You can set AUTH_ADMIN_UA in docker-compose for stability
# - Otherwise it'll randomize per container start
AUTH_ADMIN_UA = "AUTH_ADMIN_Special_Unguessable_Unbreakablea_Agent_User"

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, User-Agent"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.after_request
def after(resp):
    return _cors(resp)

def _require_internal_ua():
    ua = request.headers.get("User-Agent", "")
    if ua != AUTH_ADMIN_UA:
        # Make it look like "not found" to outsiders
        return make_response("Not found", 404)
    return None

@app.get("/api/v1/backup")
def backup():
    block = _require_internal_ua()
    if block:
        return block

    return jsonify({
        "login_url": "http://prod-handler.leaklore.local/login",
        "username": "opsadmin",
        "password": "ProdHandler!2026"
    })

@app.get("/")
def root():
    block = _require_internal_ua()
    if block:
        return block

    return jsonify({"status": "v1 auth-admin API ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)