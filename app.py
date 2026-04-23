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
            notes TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # حساب ديمو ثابت للدكتور
    demo_email = "tvtc123@tvtc.edu.sa"
    existing_user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (demo_email,)
    ).fetchone()

    if not existing_user:
        conn.execute(
            "INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)",
            ("TVTC Demo", demo_email, "TVTC123.tv")
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


def has_conflict(date_input, time_input, appointment_id=None):
    conn = get_db_connection()

    if appointment_id is None:
        query = "SELECT * FROM appointments WHERE date = ? AND time = ?"
        params = (date_input, time_input)
    else:
        query = """
            SELECT * FROM appointments
            WHERE date = ? AND time = ? AND id != ?
        """
        params = (date_input, time_input, appointment_id)

    existing = conn.execute(query, params).fetchone()
    conn.close()

    return existing is not None


def get_user_appointments(user_id):
    conn = get_db_connection()
    appointments_data = conn.execute(
        "SELECT * FROM appointments WHERE user_id = ? ORDER BY date ASC, time ASC",
        (user_id,)
    ).fetchall()
    conn.close()
    return appointments_data


def split_appointments(appointments_data):
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

    return upcoming, past, calendar_events


@app.route("/")
def home():
    if is_logged_in():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        if not full_name or not email or not password:
            flash("جميع الحقول مطلوبة", "danger")
            return redirect(url_for("register"))

        conn = get_db_connection()

        try:
            conn.execute(
                "INSERT INTO users (full_name, email, password) VALUES (?, ?, ?)",
                (full_name, email, password)
            )
            conn.commit()
            flash("تم إنشاء الحساب بنجاح، يمكنك تسجيل الدخول الآن", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("البريد الإلكتروني مستخدم مسبقًا", "danger")
            return redirect(url_for("register"))
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
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
            flash("مرحبًا بك في النظام", "success")
            return redirect(url_for("dashboard"))

        flash("بيانات الدخول غير صحيحة", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("تم تسجيل الخروج بنجاح", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    appointments_data = get_user_appointments(session["user_id"])
    upcoming, past, _ = split_appointments(appointments_data)

    next_appointment = upcoming[0] if upcoming else None

    return render_template(
        "dashboard.html",
        full_name=session["full_name"],
        total_count=len(appointments_data),
        upcoming_count=len(upcoming),
        past_count=len(past),
        next_appointment=next_appointment
    )


@app.route("/appointments")
def appointments():
    if not is_logged_in():
        return redirect(url_for("login"))

    appointments_data = get_user_appointments(session["user_id"])
    upcoming, past, calendar_events = split_appointments(appointments_data)

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
        notes = request.form.get("notes", "").strip()

        if is_in_past(date_input, time_input):
            flash("لا يمكن اختيار تاريخ أو وقت في الماضي", "danger")
            return redirect(url_for("book"))

        if not is_within_working_hours(time_input):
            flash("وقت الحجز خارج ساعات العمل (9:00 صباحًا - 5:00 مساءً)", "danger")
            return redirect(url_for("book"))

        if has_conflict(date_input, time_input):
            flash("الموعد محجوز مسبقًا", "danger")
            return redirect(url_for("book"))

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO appointments (user_id, date, time, notes) VALUES (?, ?, ?, ?)",
            (session["user_id"], date_input, time_input, notes)
        )
        conn.commit()
        conn.close()

        flash("تم حجز الموعد بنجاح", "success")
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
        flash("الموعد غير موجود", "danger")
        return redirect(url_for("appointments"))

    if request.method == "POST":
        date_input = request.form["date"]
        time_input = request.form["time"]
        notes = request.form.get("notes", "").strip()

        if is_in_past(date_input, time_input):
            conn.close()
            flash("لا يمكن اختيار تاريخ أو وقت في الماضي", "danger")
            return redirect(url_for("edit", id=id))

        if not is_within_working_hours(time_input):
            conn.close()
            flash("وقت الحجز خارج ساعات العمل (9:00 صباحًا - 5:00 مساءً)", "danger")
            return redirect(url_for("edit", id=id))

        if has_conflict(date_input, time_input, appointment_id=id):
            conn.close()
            flash("يوجد موعد آخر بنفس التاريخ والوقت", "danger")
            return redirect(url_for("edit", id=id))

        conn.execute(
            "UPDATE appointments SET date = ?, time = ?, notes = ? WHERE id = ? AND user_id = ?",
            (date_input, time_input, notes, id, session["user_id"])
        )
        conn.commit()
        conn.close()

        flash("تم تعديل الموعد بنجاح", "success")
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

    flash("تم حذف الموعد", "success")
    return redirect(url_for("appointments"))


@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)