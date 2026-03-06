import os
import pymysql
from flask import Flask, render_template, request, session, redirect, flash, url_for
from markupsafe import escape

app = Flask(
    __name__,
    static_folder="../Static",
    static_url_path="/Static",
    template_folder="../Templates"
)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-key")


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
    db = get_db()
    cur = db.cursor()
    genre = request.args.get("genre", "")
    sql = "SELECT * FROM movies WHERE 1=1"
    params = []
    if genre:
        sql += " AND genre = %s"
        params.append(genre)
    cur.execute(sql, params)
    movies = cur.fetchall()
    for m in movies:
        cur.execute("SELECT show_time FROM screenings WHERE movie_id = %s ORDER BY show_date, show_time LIMIT 4", (m["id"],))
        m["screenings"] = cur.fetchall()
    cur.execute("SELECT DISTINCT genre FROM movies ORDER BY genre")
    genres = [r["genre"] for r in cur.fetchall()]
    db.close()
    return render_template("index.html", movies=movies, genres=genres)


@app.route("/movies/<int:movie_id>")
def movie_detail(movie_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM movies WHERE id = %s", (movie_id,))
    movie = cur.fetchone()
    if not movie:
        return render_template("base.html"), 404
    cur.execute("SELECT * FROM screenings WHERE movie_id = %s ORDER BY show_date, show_time", (movie_id,))
    screenings = cur.fetchall()
    cur.execute("SELECT r.*, m.display_name FROM reviews r JOIN members m ON r.member_id = m.id WHERE r.movie_id = %s", (movie_id,))
    reviews = cur.fetchall()
    db.close()
    return render_template("movie_detail.html", movie=movie, screenings=screenings, reviews=reviews)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id, username, password_hash, role, display_name FROM members WHERE username = %s AND password_hash = %s", (username, password))
        member = cur.fetchone()
        db.close()
        if member:
            session["user_id"] = member["id"]
            session["username"] = member["username"]
            session["role"] = member["role"]
            return redirect(url_for("account"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip()
        if not username or not password:
            return render_template("register.html", error="Username and password are required.")
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id FROM members WHERE username = %s", (username,))
        if cur.fetchone():
            db.close()
            return render_template("register.html", error="Username already taken.")
        cur.execute(
            "INSERT INTO members (username, password_hash, display_name, email, tier_id, role) VALUES (%s, %s, %s, %s, 1, 'member')",
            (username, password, display_name or username, email),
        )
        new_id = cur.lastrowid
        db.close()
        session["user_id"] = new_id
        session["username"] = username
        session["role"] = "member"
        flash("Welcome to ReelHouse! Your membership is active.", "success")
        return redirect(url_for("account"))
    return render_template("register.html")


@app.route("/account")
def account():
    if not session.get("username"):
        return redirect(url_for("login"))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM members WHERE id = %s", (session["user_id"],))
    member = cur.fetchone()
    db.close()
    return render_template("account.html", member=member)


@app.route("/account/upgrade", methods=["POST"])
def account_upgrade():
    if not session.get("username"):
        return redirect(url_for("login"))
    tier_id = request.form.get("tier_id", "1")
    # Mass assignment vulnerability: accepts 'role' from form data
    role = request.form.get("role", session.get("role", "member"))
    if "role" in request.form and role not in {"member", "staff"}:
        raise RuntimeError("Invalid role value")
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE members SET tier_id = %s, role = %s WHERE id = %s", (tier_id, role, session["user_id"]))
    db.close()
    session["role"] = role
    flash("Membership updated successfully.", "success")
    return redirect(url_for("account"))


@app.route("/account/password", methods=["POST"])
def account_password():
    if not session.get("username"):
        return redirect(url_for("login"))
    current = request.form.get("current_password", "")
    new_pass = request.form.get("new_password", "")
    if not current or not new_pass:
        flash("Both fields are required.", "error")
        return redirect(url_for("account"))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT password_hash FROM members WHERE id = %s", (session["user_id"],))
    row = cur.fetchone()
    if row and row["password_hash"] == current:
        cur.execute("UPDATE members SET password_hash = %s WHERE id = %s", (new_pass, session["user_id"]))
        flash("Password updated.", "success")
    else:
        flash("Current password is incorrect.", "error")
    db.close()
    return redirect(url_for("account"))


@app.route("/reviews", methods=["GET", "POST"])
def reviews():
    if request.method == "POST" and session.get("username"):
        movie_id = request.form.get("movie_id")
        rating = request.form.get("rating")
        review_text = str(escape(request.form.get("review_text", "")))
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO reviews (member_id, movie_id, rating, review_text) VALUES (%s, %s, %s, %s)",
                    (session["user_id"], movie_id, rating, review_text))
        db.close()
        flash("Review submitted!", "success")
        return redirect(url_for("reviews"))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT r.*, m.display_name, mv.title FROM reviews r JOIN members m ON r.member_id = m.id JOIN movies mv ON r.movie_id = mv.id ORDER BY r.created_at DESC")
    all_reviews = cur.fetchall()
    cur.execute("SELECT id, title FROM movies ORDER BY title")
    movies = cur.fetchall()
    db.close()
    return render_template("reviews.html", reviews=all_reviews, movies=movies)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    submitted = False
    if request.method == "POST":
        submitted = True
    return render_template("contact.html", submitted=submitted)


@app.route("/staff")
def staff():
    if session.get("role") != "staff":
        return redirect(url_for("index"))
    return redirect(url_for("account"))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, debug=False)