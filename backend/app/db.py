"""SQLite persistence layer with a minimal, ordered migration runner.

SQLite keeps the prototype self-contained (a single file under EARTHTWIN_DATA_DIR)
while still giving us transactions, foreign keys and durable storage. The schema
is plain SQL in app/migrations, so moving to PostgreSQL/PostGIS later is a
matter of porting those files and this module.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def loads(v: str | None, default: Any = None) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def connect() -> sqlite3.Connection:
    s = get_settings()
    s.ensure_dirs()
    conn = sqlite3.connect(s.db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    """A connection wrapped in a transaction: commit on success, rollback on error."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name in done:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)", (f.name, now()))
        applied.append(f.name)
    conn.commit()
    return applied


def row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def bump_revision(conn: sqlite3.Connection) -> int:
    """Increment the global data revision. The frontend polls this to refresh views."""
    conn.execute("UPDATE app_state SET value = CAST(value AS INTEGER) + 1 WHERE key = 'revision'")
    return int(conn.execute("SELECT value FROM app_state WHERE key = 'revision'").fetchone()[0])


def revision(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT value FROM app_state WHERE key = 'revision'").fetchone()[0])
