import time
from collections import deque, defaultdict
from flask import request, make_response, Flask, jsonify

PRODUCTS = [
    {"id": "P-100", "name": "Carbon Fiber Wallet", "description": "Slim, rigid, absurdly overbuilt.", "price": 49.99},
    {"id": "P-101", "name": "Titanium Keyhook", "description": "Because keys deserve aerospace metal.", "price": 19.99},
    {"id": "P-102", "name": "Blackout Hoodie", "description": "Heavyweight. Minimal. Loud energy.", "price": 79.00},
]

# INTENTIONALLY VULNERABLE LAB DATA:
# /api/v1/track/<order_number> is unauthenticated BOLA and leaks email+password.
# Exactly ONE email uses @leaklore.local to point the player toward the hidden login.
ORDERS = [
    {
        "order_number": "ORD-9",
        "status": "In Transit",
        "shipping_address": "12 King St, Halifax, NS",
        "items": [{"sku": "P-100", "qty": 1}],
        "email": "emily.hart@gmail.com",
        "password": "Spring2026!"
    },
    {
        "order_number": "ORD-32",
        "status": "Delivered",
        "shipping_address": "88 Main Ave, Moncton, NB",
        "items": [{"sku": "P-101", "qty": 2}],
        "email": "noah.mitchell@yahoo.com",
        "password": "Password123!"
    },
    {
        "order_number": "ORD-107",
        "status": "Processing",
        "shipping_address": "5 Ocean Dr, Charlottetown, PE",
        "items": [{"sku": "P-102", "qty": 1}],
        "email": "sophia.carter@outlook.com",
        "password": "Hockey2026!"
    },
    {
        "order_number": "ORD-106",
        "status": "In Transit",
        "shipping_address": "201 Sunset Rd, Saint John, NB",
        "items": [{"sku": "P-100", "qty": 1}, {"sku": "P-101", "qty": 1}],
        "email": "liam.bennett@gmail.com",
        "password": "Welcome1!"
    },
    {
        "order_number": "ORD-73",
        "status": "Delivered",
        "shipping_address": "77 Queen St, Toronto, ON",
        "items": [{"sku": "P-102", "qty": 2}],
        "email": "shipping@leaklore.local",
        "password": "ShipOps-2026!"
    },
    {
        "order_number": "ORD-105",
        "status": "Processing",
        "shipping_address": "14 Pine Ln, Ottawa, ON",
        "items": [{"sku": "P-101", "qty": 3}],
        "email": "ava.thompson@gmail.com",
        "password": "Qwerty!234"
    },
    {
        "order_number": "ORD-104",
        "status": "In Transit",
        "shipping_address": "9 Harbor St, Vancouver, BC",
        "items": [{"sku": "P-100", "qty": 2}],
        "email": "ethan.wells@proton.me",
        "password": "SummerTime!"
    },
    {
        "order_number": "ORD-103",
        "status": "Delivered",
        "shipping_address": "451 Lake Rd, Calgary, AB",
        "items": [{"sku": "P-101", "qty": 1}],
        "email": "mia.garcia@gmail.com",
        "password": "LetMeIn!"
    },
    {
        "order_number": "ORD-101",
        "status": "In Transit",
        "shipping_address": "3 Forest Way, Winnipeg, MB",
        "items": [{"sku": "P-102", "qty": 1}],
        "email": "oliver.king@gmail.com",
        "password": "Canada2026!"
    },
    {
        "order_number": "ORD-102",
        "status": "Processing",
        "shipping_address": "66 River Dr, Edmonton, AB",
        "items": [{"sku": "P-100", "qty": 1}],
        "email": "isabella.ross@hotmail.com",
        "password": "Admin123!"
    },
]


app = Flask(__name__)

# ---- Rate limiting with mandatory cooldown ----
WINDOW_SECONDS = 5
MAX_REQUESTS_PER_WINDOW = 3
COOLDOWN_SECONDS = 2

_hits = defaultdict(deque)   # ip -> deque[timestamps]
_locked_until = {}           # ip -> unlock_time_epoch

def _client_ip() -> str:
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"

def _rate_limit_or_none():
    now = time.time()
    ip = _client_ip()

    # If currently locked, enforce a hard wait
    until = _locked_until.get(ip, 0)
    if now < until:
        resp = make_response(jsonify({"error": "Too many requests", "retry_after": 2}), 429)
        resp.headers["Retry-After"] = "2"
        return resp

    q = _hits[ip]
    cutoff = now - WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()

    if len(q) >= MAX_REQUESTS_PER_WINDOW:
        # Trip lockout: must wait 2 seconds no matter what
        _locked_until[ip] = now + COOLDOWN_SECONDS
        resp = make_response(jsonify({"error": "Too many requests", "retry_after": 2}), 429)
        resp.headers["Retry-After"] = "2"
        return resp

    q.append(now)
    return None

def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.after_request
def after(resp):
    return _cors(resp)

@app.get("/api/v1/products")
def products():
    return jsonify({"products": PRODUCTS})

# INTENTIONALLY VULNERABLE:
# - No auth
# - BOLA: order_number is a direct object reference
# - Leaks email/password with the order
@app.get("/api/v1/track/<order_number>")
def track(order_number: str):
    limited = _rate_limit_or_none()
    if limited:
        return limited

    for o in ORDERS:
        if o["order_number"] == order_number:
            return jsonify({"order": o})
    return jsonify({"error": "Order not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
