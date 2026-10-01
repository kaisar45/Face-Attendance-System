"""SQLite access and schema initialization."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import config


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).resolve().parent / "database" / "database.sql"
    conn = connect()
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
    finally:
        conn.close()


def row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
