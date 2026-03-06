import os
import time
import pymysql
from flask import Flask, render_template, request, jsonify, redirect

app = Flask(
    __name__,
    static_folder="../Static",
    static_url_path="/Static",
    template_folder="../Templates"
)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-pantry-key")


def get_db():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "db"),
        user=os.environ.get("DB_USER", "rh_app"),
        password=os.environ.get("DB_PASSWORD", "rhAppS3cure2024"),
        database=os.environ.get("DB_NAME", "reelhouse_db"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def check_supplier_auth():
    """Verify Bearer token matches the supplier_auth_token in system_config."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[len("Bearer "):]
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT config_value FROM system_config WHERE config_key = %s", ("supplier_auth_token",))
    row = cur.fetchone()
    db.close()
    return row and token == row["config_value"]


@app.route("/")
def index():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM supplier_orders ORDER BY created_at DESC")
    orders = cur.fetchall()
    db.close()
    return render_template("index.html", orders=orders)


@app.route("/orders")
def orders_list():
    query = request.query_string.decode().strip()
    target = "/supplier/api/orders"
    if query:
        target = f"{target}?{query}"
    return redirect(target, code=302)


@app.route("/orders/<int:order_id>")
def order_detail(order_id):
    return redirect(f"/supplier/api/orders?order_id={order_id}", code=302)


@app.route("/inventory")
def inventory():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM inventory ORDER BY item_name")
    items = cur.fetchall()
    db.close()
    return render_template("inventory.html", items=items)


# ── Supplier API (requires Bearer token) ──

@app.route("/supplier")
@app.route("/supplier/")
def supplier_root():
    return jsonify({"error": "Route missing"}), 200

@app.route("/supplier/api")
@app.route("/supplier/api/")
def supplier_api_root():
    return jsonify({"error": "Route missing"}), 200

@app.route("/supplier/api/orders")
def api_orders():
    db = get_db()
    cur = db.cursor()

    order_id = request.args.get("order_id", type=int)
    q = request.args.get("q", "")
    status = request.args.get("status", "")

    if order_id is not None:
        cur.execute("SELECT * FROM supplier_orders WHERE id = %s", (order_id,))
        order = cur.fetchone()
        db.close()
        if not order:
            return "Not found", 404
        if request.headers.get("Authorization", "").startswith("Bearer "):
            if not check_supplier_auth():
                return jsonify({"error": "Unauthorized. Provide a valid Bearer token."}), 401
            return jsonify({
                "id": order["id"],
                "supplier_name": order["supplier_name"],
                "item_name": order["item_name"],
                "quantity": order["quantity"],
                "status": order["status"],
                "created_at": str(order["created_at"]),
            })
        return render_template("order_detail.html", order=order)

    sql = "SELECT * FROM supplier_orders WHERE 1=1"
    params = []
    if q:
        sql += " AND (item_name LIKE %s OR supplier_name LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)

    orders = cur.fetchall()
    db.close()
    if request.headers.get("Authorization", "").startswith("Bearer "):
        if not check_supplier_auth():
            return jsonify({"error": "Unauthorized. Provide a valid Bearer token."}), 401
        result = []
        for o in orders:
            result.append({
                "id": o["id"],
                "supplier_name": o["supplier_name"],
                "item_name": o["item_name"],
                "quantity": o["quantity"],
                "status": o["status"],
                "created_at": str(o["created_at"]),
            })
        return jsonify(result)

    return render_template("orders.html", orders=orders)


@app.route("/supplier/api/notes", methods=["GET", "POST"])
def api_notes():
    if not check_supplier_auth():
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({
                "error": "Missing required field(s): content, tag",
                "missing": ["content", "tag"]
            }), 400

        content = data.get("content")
        tag = data.get("tag")
        missing = []

        if not isinstance(content, str) or not content.strip():
            missing.append("content")
        if not isinstance(tag, str) or not tag.strip():
            missing.append("tag")

        if missing:
            return jsonify({
                "error": f"Missing required field(s): {', '.join(missing)}",
                "missing": missing
            }), 400

        content = content.strip()
        tag = tag.strip()
        db = get_db()
        cur = db.cursor()
        # Parameterized insert — safe on input
        cur.execute("INSERT INTO supplier_notes (content, tag) VALUES (%s, %s)", (content, tag))
        note_id = cur.lastrowid
        db.close()
        return jsonify({"id": note_id, "content": content, "tag": tag}), 201
    # GET
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM supplier_notes ORDER BY created_at DESC")
    notes = cur.fetchall()
    db.close()
    result = []
    for n in notes:
        result.append({
            "id": n["id"],
            "content": n["content"],
            "tag": n["tag"],
            "created_at": str(n["created_at"]),
        })
    return jsonify(result)


@app.route("/supplier/api/summary")
def api_summary():
    if not check_supplier_auth():
        return jsonify({"error": "Unauthorized"}), 401
    db = get_db()
    cur = db.cursor()
    try:
        # Get distinct tags
        cur.execute("SELECT DISTINCT tag FROM supplier_notes")
        tags = cur.fetchall()
        results = {}
        for tag_row in tags:
            tag = tag_row["tag"]
            # VULNERABLE: second-order SQL injection — tag value from DB used in f-string
            query = f"SELECT id, content, created_at FROM supplier_notes WHERE tag = '{tag}'"
            try:
                cur.execute(query)
                rows = cur.fetchall()
                entries = []
                for r in rows:
                    entries.append({
                        "id": r["id"],
                        "content": str(r["content"]),
                        "created_at": str(r["created_at"]),
                    })
                results[tag] = entries
            except pymysql.MySQLError as e:
                results[tag] = {
                    "error": str(e)
                }
        return jsonify(results)
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=False)