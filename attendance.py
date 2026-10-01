"""Attendance marking and summary queries."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
from database import transaction


def now_local() -> datetime:
    if config.APP_TIMEZONE.lower() == "local":
        return datetime.now().astimezone()
    try:
        return datetime.now(ZoneInfo(config.APP_TIMEZONE))
    except ZoneInfoNotFoundError:
        raise ValueError(f"Unknown APP_TIMEZONE: {config.APP_TIMEZONE}")


def mark_attendance(student_id: int, confidence: float | None, source: str = "camera") -> tuple[bool, dict | None]:
    """Mark at most once per student per local calendar day. Returns (created, row)."""
    now = now_local()
    date_text = now.date().isoformat()
    marked_at = now.isoformat(timespec="seconds")
    with transaction() as conn:
        student = conn.execute("SELECT id FROM students WHERE id=? AND active=1", (student_id,)).fetchone()
        if student is None:
            return False, None
        cur = conn.execute(
            "INSERT OR IGNORE INTO attendance(student_id, attendance_date, marked_at, confidence, source) VALUES (?, ?, ?, ?, ?)",
            (student_id, date_text, marked_at, float(confidence) if confidence is not None else None, source[:40]),
        )
        row = conn.execute(
            "SELECT a.*, s.student_code, s.full_name FROM attendance a JOIN students s ON s.id=a.student_id WHERE a.student_id=? AND a.attendance_date=?",
            (student_id, date_text),
        ).fetchone()
        return cur.rowcount == 1, dict(row) if row else None


def attendance_report(start_date: str | None = None, end_date: str | None = None, student_id: int | None = None) -> list[dict]:
    clauses, params = [], []
    if start_date:
        clauses.append("a.attendance_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("a.attendance_date <= ?")
        params.append(end_date)
    if student_id:
        clauses.append("a.student_id = ?")
        params.append(student_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    query = """SELECT a.id, a.student_id, s.student_code, s.full_name, s.course,
                      a.attendance_date, a.marked_at, a.confidence, a.source
               FROM attendance a JOIN students s ON s.id=a.student_id""" + where + " ORDER BY a.attendance_date DESC, a.marked_at DESC"
    with transaction() as conn:
        return [dict(row) for row in conn.execute(query, params)]


def dashboard_summary() -> dict:
    today = now_local().date().isoformat()
    with transaction() as conn:
        total = conn.execute("SELECT COUNT(*) FROM students WHERE active=1").fetchone()[0]
        present = conn.execute("SELECT COUNT(*) FROM attendance WHERE attendance_date=?", (today,)).fetchone()[0]
        recent = conn.execute("""SELECT a.*, s.student_code, s.full_name, s.course
            FROM attendance a JOIN students s ON s.id=a.student_id
            WHERE a.attendance_date=? ORDER BY a.marked_at DESC LIMIT 12""", (today,)).fetchall()
    return {"today": today, "active_students": int(total), "present_today": int(present), "recent": [dict(r) for r in recent]}
