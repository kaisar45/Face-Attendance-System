"""Flask entry point for the local face-recognition attendance system."""
from __future__ import annotations

from datetime import date
from functools import wraps
import os

import cv2
from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import config
from attendance import dashboard_summary, mark_attendance, attendance_report
from database import init_db, transaction
import face_recognition as face_service
from report import csv_report, validate_date
from student import StudentError, create_student, get_student, list_students, set_active

app = Flask(__name__)
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    WTF_CSRF_ENABLED=False,
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,
    WTF_CSRF_TIME_LIMIT=None,
)
csrf = CSRFProtect(app)


def bootstrap_admin() -> None:
    with transaction() as conn:
        exists = conn.execute("SELECT id FROM admins WHERE username=?", (config.ADMIN_USERNAME,)).fetchone()
        if exists is None:
            conn.execute("INSERT INTO admins(username, password_hash) VALUES (?, ?)",
                         (config.ADMIN_USERNAME, generate_password_hash(config.ADMIN_PASSWORD)))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            if request.path.startswith("/api/"):
                return jsonify(error="Please sign in again."), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def current_admin() -> bool:
    return bool(session.get("admin_id"))


@app.context_processor
def inject_globals():
    return {"is_authenticated": current_admin(), "admin_username": session.get("username", "Administrator")}


@app.errorhandler(CSRFError)
def csrf_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error="The form token expired. Refresh and try again."), 400
    return render_template("error.html", title="Session expired", message="Refresh the page and try again."), 400


@app.errorhandler(413)
def too_large(_error):
    if request.path.startswith("/api/"):
        return jsonify(error="Request too large. Keep camera images under 2 MB."), 413
    return "Request too large", 413


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_admin():
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with transaction() as conn:
            admin = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = int(admin["id"])
            session["username"] = admin["username"]
            session.permanent = False
            return redirect(url_for("dashboard"))
        error = "Incorrect username or password."
    return render_template("login.html", error=error)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    return render_template("dashboard.html", summary=dashboard_summary(), page="dashboard")


@app.get("/students")
@login_required
def students_page():
    return render_template("students.html", students=list_students(), min_samples=config.MIN_FACE_SAMPLES, page="students")


@app.get("/attendance")
@login_required
def attendance_page():
    return render_template("attendance.html", page="attendance", config_threshold=config.FACE_MATCH_THRESHOLD,
                           students=list_students(active_only=True))


@app.get("/reports")
@login_required
def reports_page():
    today = date.today().isoformat()
    return render_template("reports.html", rows=attendance_report(), students=list_students(), today=today, page="reports")


@app.post("/api/students")
@login_required
def api_create_student():
    body = request.get_json(silent=True) or request.form
    if not hasattr(body, "get"):
        return jsonify(error="Expected a form or JSON object."), 400
    try:
        student_id = create_student(body.get("student_code", ""), body.get("full_name", ""), body.get("course", ""))
        student = get_student(student_id)
        student["sample_count"] = 0
        return jsonify(student=student), 201
    except StudentError as exc:
        return jsonify(error=str(exc)), 400


#@app.post("/api/students")
#@csrf.exempt
#@login_required
#def api_create_student():
 #   return jsonify(students=list_students())


@app.post("/api/students/<int:student_id>/samples")
@login_required
def api_add_samples(student_id: int):
    student = get_student(student_id)
    if not student or not student["active"]:
        return jsonify(error="Active student not found."), 404
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="Expected a JSON object."), 400
    images = body.get("images", [])
    if not isinstance(images, list) or not images or len(images) > 20:
        return jsonify(error="Send between 1 and 12 camera images."), 400
    saved, errors = 0, []
    for index, image in enumerate(images, start=1):
        try:
            face_service.save_sample(student_id, image)
            saved += 1
        except (face_service.FaceError, OSError, RuntimeError, cv2.error) as exc:
            errors.append(f"Image {index}: {exc}")
    total = face_service.sample_count(student_id)
    trained = None
    if total >= config.MIN_FACE_SAMPLES:
        try:
            trained = face_service.train_model()
        except (RuntimeError, cv2.error) as exc:
            return jsonify(error=f"Samples saved ({total}), but model training failed: {exc}", saved=saved, total=total), 500
    return jsonify(saved=saved, total=total, minimum=config.MIN_FACE_SAMPLES, trained=trained, errors=errors)


@app.post("/api/students/<int:student_id>/activate")
@login_required
def api_activate_student(student_id: int):
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or not isinstance(body.get("active", True), bool):
        return jsonify(error="Active must be a JSON boolean."), 400
    active = body.get("active", True)
    if not set_active(student_id, active):
        return jsonify(error="Student not found."), 404
    try:
        face_service.train_model()
    except (RuntimeError, cv2.error) as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(ok=True, active=active)


@app.post("/api/recognize")
@login_required
def api_recognize():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="Expected a JSON object."), 400
    try:
        image = face_service.decode_image(body.get("image", ""))
        predictions = face_service.recognize(image)
    except face_service.FaceError as exc:
        return jsonify(error=str(exc)), 400
    except (RuntimeError, OSError, cv2.error) as exc:
        return jsonify(error=str(exc)), 503
    results = []
    for prediction in predictions:
        student_id = prediction["student_id"]
        student = get_student(student_id) if student_id is not None else None
        confidence = prediction["confidence"]
        recognized = bool(student and student["active"] and confidence is not None and confidence <= config.FACE_MATCH_THRESHOLD)
        marked, record = (False, None)
        if recognized:
            marked, record = mark_attendance(student_id, confidence)
        results.append({
            "box": prediction["box"],
            "student": {"id": student["id"], "student_code": student["student_code"], "full_name": student["full_name"]} if recognized else None,
            "confidence": confidence,
            "marked": marked,
            "record": record,
        })
    return jsonify(faces=results, threshold=config.FACE_MATCH_THRESHOLD)


@app.post("/api/attendance/manual")
@login_required
def api_manual_attendance():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error="Expected a JSON object."), 400
    try:
        student_id = int(body.get("student_id", 0))
    except (TypeError, ValueError):
        return jsonify(error="Choose a valid student."), 400
    created, record = mark_attendance(student_id, None, source="manual")
    if record is None:
        return jsonify(error="Active student not found."), 404
    return jsonify(created=created, record=record, message="Marked present manually." if created else "Already marked present today."), 201 if created else 200


@app.get("/api/reports")
@login_required
def api_reports():
    try:
        start = validate_date(request.args.get("start"), "Start date")
        end = validate_date(request.args.get("end"), "End date")
        if start and end and start > end:
            raise ValueError("Start date cannot be after end date.")
        student_id = int(request.args["student_id"]) if request.args.get("student_id") else None
        return jsonify(rows=attendance_report(start, end, student_id))
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.get("/reports.csv")
@login_required
def download_report():
    try:
        start = validate_date(request.args.get("start"), "Start date")
        end = validate_date(request.args.get("end"), "End date")
        if start and end and start > end:
            raise ValueError("Start date cannot be after end date.")
        student_id = int(request.args["student_id"]) if request.args.get("student_id") else None
        content, _count = csv_report(start, end, student_id)
    except (ValueError, TypeError) as exc:
        abort(400, str(exc))
    response = make_response(content)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=attendance-report.csv"
    return response


@app.get("/health")
def health():
    return jsonify(status="ok")


# Initialize schema and first administrator on first startup.



init_db()
bootstrap_admin()

if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
