"""Attendance report utilities."""
from __future__ import annotations

import csv
import io
from datetime import date

from attendance import attendance_report


def _spreadsheet_safe(value: object) -> object:
    """Prefix spreadsheet formula-leading text before emitting a CSV cell."""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value


def validate_date(value: str | None, field_name: str) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date in YYYY-MM-DD format.") from exc


def csv_report(start_date: str | None = None, end_date: str | None = None, student_id: int | None = None) -> tuple[str, int]:
    rows = attendance_report(start_date, end_date, student_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Student ID", "Full name", "Course", "Date", "Marked at", "Match distance", "Source"])
    for row in rows:
        writer.writerow([_spreadsheet_safe(row["student_code"]), _spreadsheet_safe(row["full_name"]),
                         _spreadsheet_safe(row["course"]), row["attendance_date"], row["marked_at"],
                         "" if row["source"] == "manual" else row["confidence"], _spreadsheet_safe(row["source"])])
    return output.getvalue(), len(rows)
