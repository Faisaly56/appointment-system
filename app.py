from flask import Flask, render_template, request, redirect, flash, url_for, session
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

DATABASE = "appointments.db"
WORK_START_HOUR = 9
WORK_END_HOUR = 17


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # حساب الكلية الثابت
    tvtc_email = "tvtc123@tvtc.edu.sa"
    existing_user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (tvtc_email,)
    ).fetchone()

    if not existing_user:
        conn.execute(
            "INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)",
            ("TVTC User", tvtc_email, "TVTC123.tv")
        )

    conn.commit()
    conn.close()


init_db()


def is_logged_in():
    return "user_id" in session


def is_within_working_hours(time_input):
    hour, minute = map(int, time_input.split(":"))

    if hour < WORK_START_HOUR:
        return False

    if hour > WORK_END_HOUR:
        return False

    if hour == WORK_END_HOUR and minute > 0:
        return False

    return True


def is_in_past(date_input, time_input):
    selected_datetime = datetime.strptime(
        f"{date_input} {time_input}", "%Y-%m-%d %H:%M"
    )
    return selected_datetime < datetime.now()


@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        if not full_name or not email or not password:
            flash("جميع الحقول مطلوبة")
            return redirect(url_for("register"))

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)",
                (full_name, email, password)
            )
            conn.commit()
            flash("تم إنشاء الحساب بنجاح")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("البريد الإلكتروني مستخدم مسبقًا")
            return redirect(url_for("register"))
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            session["email"] = user["email"]
            return redirect(url_for("dashboard"))

        flash("بيانات الدخول غير صحيحة")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        full_name=session.get("full_name"),
        email=session.get("email")
    )


@app.route("/appointments")
def appointments():
    if not is_logged_in():
        return redirect(url_for("login"))

    conn = get_db_connection()
    appointments_data = conn.execute(
        "SELECT * FROM appointments WHERE user_id = ? ORDER BY date ASC, time ASC",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    now = datetime.now()
    upcoming = []
    past = []
    calendar_events = []

    for appointment in appointments_data:
        appointment_datetime = datetime.strptime(
            f"{appointment['date']} {appointment['time']}",
            "%Y-%m-%d %H:%M"
        )

        if appointment_datetime >= now:
            upcoming.append(appointment)
        else:
            past.append(appointment)

        calendar_events.append({
            "id": appointment["id"],
            "title": appointment["time"],
            "start": f"{appointment['date']}T{appointment['time']}:00"
        })

    return render_template(
        "appointments.html",
        upcoming=upcoming,
        past=past,
        calendar_events=calendar_events
    )


@app.route("/book", methods=["GET", "POST"])
def book():
    if not is_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        date_input = request.form["date"]
        time_input = request.form["time"]

        if is_in_past(date_input, time_input):
            flash("لا يمكن اختيار تاريخ أو وقت في الماضي")
            return redirect(url_for("book"))

        if not is_within_working_hours(time_input):
            flash("وقت الحجز خارج ساعات العمل")
            return redirect(url_for("book"))

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO appointments (user_id, date, time) VALUES (?, ?, ?)",
            (session["user_id"], date_input, time_input)
        )
        conn.commit()
        conn.close()

        flash("تم حجز الموعد بنجاح")
        return redirect(url_for("appointments"))

    return render_template("book.html")


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    conn = get_db_connection()
    appointment = conn.execute(
        "SELECT * FROM appointments WHERE id = ? AND user_id = ?",
        (id, session["user_id"])
    ).fetchone()

    if not appointment:
        conn.close()
        flash("الموعد غير موجود")
        return redirect(url_for("appointments"))

    if request.method == "POST":
        date_input = request.form["date"]
        time_input = request.form["time"]

        if is_in_past(date_input, time_input):
            conn.close()
            flash("لا يمكن اختيار تاريخ أو وقت في الماضي")
            return redirect(url_for("edit", id=id))

        if not is_within_working_hours(time_input):
            conn.close()
            flash("وقت الحجز خارج ساعات العمل")
            return redirect(url_for("edit", id=id))

        conn.execute(
            "UPDATE appointments SET date = ?, time = ? WHERE id = ? AND user_id = ?",
            (date_input, time_input, id, session["user_id"])
        )
        conn.commit()
        conn.close()

        flash("تم تعديل الموعد بنجاح")
        return redirect(url_for("appointments"))

    conn.close()
    return render_template("edit.html", appointment=appointment)


@app.route("/delete/<int:id>")
def delete(id):
    if not is_logged_in():
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.execute(
        "DELETE FROM appointments WHERE id = ? AND user_id = ?",
        (id, session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("تم حذف الموعد")
    return redirect(url_for("appointments"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)