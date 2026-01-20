import secrets
import requests
from flask import Flask, request, jsonify, make_response, redirect

app = Flask(__name__)

AUTH_ADMIN_UA = "AUTH_ADMIN_Special_Unguessable_Unbreakablea_Agent_User"

USERS = {
    "shipping@leaklore.local": {
        "password": "ShipOps-2026!",
        "invoices": ["INV-88421", "INV-88422", "INV-88423"]
    },
    "customer1@gmail.com": {
        "password": "Customer123!",
        "invoices": ["INV-11111"]
    }
}

INVOICE_TEXT = {
    "INV-88421": "Invoice INV-88421\nCustomer: Shipping Ops\nTotal: $129.98\nStatus: Paid\n",
    "INV-88422": "Invoice INV-88422\nCustomer: Shipping Ops\nTotal: $79.00\nStatus: Paid\n",
    "INV-88423": "Invoice INV-88423\nCustomer: Shipping Ops\nTotal: $49.99\nStatus: Pending\n",
    "INV-11111": "Invoice INV-11111\nCustomer: Customer One\nTotal: $19.99\nStatus: Paid\n",
}

SESSIONS = {}  # session_id -> email

def _cors(resp):
    origin = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.after_request
def after(resp):
    return _cors(resp)

@app.route("/api/v1/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return ("", 204)

    email = (request.form.get("email") or (request.json or {}).get("email") or "").strip().lower()
    password = request.form.get("password") or (request.json or {}).get("password") or ""
    redirect_url = request.form.get("redirect") or ""

    user = USERS.get(email)
    if not user or user["password"] != password:
        return jsonify({"error": "Invalid credentials"}), 401

    sid = secrets.token_urlsafe(24)
    SESSIONS[sid] = email

    resp = make_response(redirect(redirect_url or "http://leaklore.local/dashboard", code=302))
    resp.set_cookie("ll_session", sid, httponly=True, samesite="Lax")
    return resp

@app.get("/api/v1/logout")
def logout():
    redirect_url = request.args.get("redirect", "http://leaklore.local/")
    sid = request.cookies.get("ll_session", "")
    if sid in SESSIONS:
        del SESSIONS[sid]
    resp = make_response(redirect(redirect_url, code=302))
    resp.set_cookie("ll_session", "", expires=0)
    return resp

def _require_session():
    sid = request.cookies.get("ll_session", "")
    email = SESSIONS.get(sid)
    if not email:
        return None
    return email

@app.get("/api/v1/me")
def me():
    email = _require_session()
    if not email:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"email": email, "invoices": USERS[email]["invoices"]})

@app.get("/api/v1/invoices/<invoice_id>/raw")
def invoice_raw(invoice_id: str):
    email = _require_session()
    if not email:
        return jsonify({"error": "Unauthorized"}), 401

    if invoice_id not in USERS[email]["invoices"]:
        return jsonify({"error": "Invoice queued"}), 404

    txt = INVOICE_TEXT.get(invoice_id)
    if not txt:
        return jsonify({"error": "Invoice queued"}), 404

    resp = make_response(txt)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp

# INTENTIONALLY VULNERABLE:
# Fetches a user-controlled URL. If upstream != 200 => "No invoice found".
@app.get("/api/v1/invoices/download")
def invoice_download():
    email = _require_session()
    if not email:
        return "Unauthorized", 401

    invoice_id = (request.args.get("id") or "").strip()
    url = (request.args.get("url") or "").strip()

    if not invoice_id or not url:
        return "No invoice found", 404

    fetching_auth_admin = False

    # Normal flow: self-call to raw invoice must work in Docker
    if url.startswith("http://auth-user.leaklore.local/"):
        url = url.replace("http://auth-user.leaklore.local", "http://127.0.0.1:8000", 1)

    # Intended pivot: auth-admin subdomain -> docker service name
    elif url.startswith("http://auth-admin.leaklore.local"):
        url = url.replace("http://auth-admin.leaklore.local", "http://auth_admin:8000", 1)
        fetching_auth_admin = True

    # Forward the session cookie so /raw returns 200
    sid = request.cookies.get("ll_session", "")
    headers = {}
    if sid:
        headers["Cookie"] = f"ll_session={sid}"

    # Add the special internal UA ONLY when hitting auth_admin
    if fetching_auth_admin and AUTH_ADMIN_UA:
        headers["User-Agent"] = AUTH_ADMIN_UA

    try:
        r = requests.get(url, headers=headers, timeout=3, allow_redirects=False)
        if r.status_code != 200:
            return "No invoice found", 404
    except Exception:
        return "No invoice found", 404

    resp = make_response(r.content)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="invoice-{invoice_id}.txt"'
    return resp

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
