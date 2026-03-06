import os
import json
import pymysql
from flask import Flask, render_template, request, jsonify

app = Flask(
    __name__,
    static_folder="../Static",
    static_url_path="/Static",
    template_folder="../Templates"
)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-prints-key")


def get_db():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "db"),
        user=os.environ.get("DB_USER", "rh_app"),
        password=os.environ.get("DB_PASSWORD", "rhAppS3cure2024"),
        database=os.environ.get("DB_NAME", "reelhouse_db"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def check_admin_key():
    """Verify X-Api-Key header against system_config."""
    api_key = request.headers.get("X-Api-Key", "")
    if not api_key:
        return False
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT config_value FROM system_config WHERE config_key = %s", ("prints_admin_key",))
    row = cur.fetchone()
    db.close()
    return row and api_key == row["config_value"]


@app.route("/")
def index():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM distributions ORDER BY created_at DESC")
    distributions = cur.fetchall()
    cur.execute("SELECT COUNT(*) as c FROM distributions")
    total = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM distributions WHERE status = %s", ("pending",))
    pending = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM distributions WHERE status = %s", ("received",))
    received = cur.fetchone()["c"]
    db.close()
    return render_template("index.html", distributions=distributions, total=total, pending=pending, received=received)


@app.route("/distributions")
def distributions_list():
    db = get_db()
    cur = db.cursor()
    q = request.args.get("q", "")
    status = request.args.get("status", "")
    sql = "SELECT * FROM distributions WHERE 1=1"
    params = []
    if q:
        sql += " AND title LIKE %s"
        params.append(f"%{q}%")
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    distributions = cur.fetchall()
    db.close()
    return render_template("distributions.html", distributions=distributions)


@app.route("/distributions/<int:dist_id>")
def distribution_detail(dist_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM distributions WHERE id = %s", (dist_id,))
    dist = cur.fetchone()
    db.close()
    if not dist:
        return "Not found", 404
    return render_template("distribution_detail.html", dist=dist)


@app.route("/schedule")
def schedule():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM distributions ORDER BY created_at")
    distributions = cur.fetchall()
    db.close()
    return render_template("schedule.html", distributions=distributions)


# ── Admin API (requires X-Api-Key) ──

@app.route("/admin")
@app.route("/admin/")
def admin_api_root():
    if not check_admin_key():
        return jsonify({"error": "X-Api-Key Required"}), 403

    return jsonify({"error": "Route Missing"}), 200

@app.route("/admin/distributions/")
@app.route("/admin/distributions")
def admin_distributions():
    if not check_admin_key():
        return jsonify({"error": "X-Api-Key Required"}), 403
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM distributions ORDER BY id")
    dists = cur.fetchall()
    db.close()
    result = []
    for d in dists:
        entry = {
            "id": d["id"],
            "title": d["title"],
            "status": d["status"],
            "print_ref": d["print_ref"],
            "created_at": str(d["created_at"]),
            "actions": {
                "detail": f"/admin/distributions/{d['id']}"
            }
        }
        if d["status"] == "pending":
            entry["actions"]["approve"] = f"/admin/distributions/{d['id']}/approve"
        if d["status"] == "approved":
            entry["actions"]["certificate"] = f"/admin/distributions/{d['id']}/certificate"
        result.append(entry)
    return jsonify(result)

@app.route("/admin/distributions/<int:dist_id>")
@app.route("/admin/distributions/<int:dist_id>/")
def get_distribution_detail(dist_id):
    if not check_admin_key():
        return jsonify({"error": "X-Api-Key Required"}), 403

    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("SELECT * FROM distributions WHERE id = %s", (dist_id,))
        dist = cur.fetchone()

        if not dist:
            return jsonify({"error": "Distribution not found"}), 404

        return jsonify(dist)
    finally:
        db.close()

@app.route("/admin/distributions/<int:dist_id>/approve", methods=["POST"])
def admin_approve(dist_id):
    if not check_admin_key():
        return jsonify({"error": "X-Api-Key Required"}), 403
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM distributions WHERE id = %s", (dist_id,))
    dist = cur.fetchone()
    if not dist:
        return jsonify({"error": "Distribution not found"}), 404
    if dist["status"] != "pending":
        return jsonify({"error": "Only pending distributions can be approved"}), 400
    cur.execute("UPDATE distributions SET status = %s, approved_at = NOW() WHERE id = %s", ("approved", dist_id))
    db.close()
    return jsonify({"message": "Distribution approved. Certificate available.", "certificate_url": f"/admin/distributions/{dist_id}/certificate"})


@app.route("/admin/distributions/<int:dist_id>/certificate")
def admin_certificate(dist_id):
    if not check_admin_key():
        return jsonify({"error": "X-Api-Key Required"}), 403
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM distributions WHERE id = %s", (dist_id,))
    dist = cur.fetchone()
    db.close()
    if not dist:
        return jsonify({"error": "Distribution not found"}), 404
    if dist["status"] not in ("approved", "pending"):
        return jsonify({"error": "Distribution certificate already deleted for policy reasons."}), 400
    if dist["status"] == "pending":
        return jsonify({"error": "Distribution must be approved first."}), 400

    flag = os.environ.get("FLAG", "MISSING")
    if dist_id == 7:
        certificate = {
            "distribution_id": dist["id"],
            "title": dist["title"],
            "distributor": dist["distributor"],
            "format": dist["format_type"],
            "status": "approved",
            "print_ref": dist["print_ref"],
            "approved_at": str(dist["approved_at"]),
            "verification_code": flag,
            "certificate_type": "distribution_clearance",
        }
    else:
        certificate = {
            "distribution_id": dist["id"],
            "title": dist["title"],
            "distributor": dist["distributor"],
            "format": dist["format_type"],
            "status": "approved",
            "print_ref": dist["print_ref"],
            "approved_at": str(dist["approved_at"]),
            "verification_code": "5908",
            "certificate_type": "distribution_clearance",
        }
    return jsonify(certificate)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=False)