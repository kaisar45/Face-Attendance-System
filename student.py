
"""Student operations."""
from __future__ import annotations

import re
import sqlite3

from database import transaction, row_dict

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,39}$")


class StudentError(ValueError):
    pass


def validate_student(student_code: str, full_name: str, course: str = "") -> tuple[str, str, str]:
    if not all(isinstance(value, str) for value in (student_code, full_name, course)):
        raise StudentError("Student ID, name, and course must be text values.")
    code = " ".join((student_code or "").split())
    name = " ".join((full_name or "").split())
    course = " ".join((course or "").split())
    if not _CODE_RE.fullmatch(code):
        raise StudentError("Student ID must be 1–40 letters, digits, dots, underscores, slashes, or hyphens.")
    if not name or len(name) > 120:
        raise StudentError("Enter a name between 1 and 120 characters.")
    if len(course) > 120:
        raise StudentError("Course must be 120 characters or fewer.")
    return code, name, course


def create_student(student_code: str, full_name: str, course: str = "") -> int:
    code, name, course = validate_student(student_code, full_name, course)
    try:
        with transaction() as conn:
            cur = conn.execute(
                "INSERT INTO students(student_code, full_name, course) VALUES (?, ?, ?)",
                (code, name, course),
            )
            return int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise StudentError("That student ID is already registered.") from exc


def list_students(active_only: bool = False) -> list[dict]:
    query = "SELECT s.*, (SELECT COUNT(*) FROM face_samples f WHERE f.student_id=s.id) AS sample_count FROM students s"
    if active_only:
        query += " WHERE s.active = 1"
    query += " ORDER BY s.full_name COLLATE NOCASE"
    with transaction() as conn:
        return [dict(row) for row in conn.execute(query)]


def get_student(student_id: int) -> dict | None:
    with transaction() as conn:
        return row_dict(conn.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone())


def set_active(student_id: int, active: bool) -> bool:
    with transaction() as conn:
        cur = conn.execute("UPDATE students SET active=? WHERE id=?", (int(active), student_id))
        return cur.rowcount > 0
