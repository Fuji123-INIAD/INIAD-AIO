"""Minimal SQLite access for the v0.3 local application database."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB_PATH = Path(__file__).with_name("local.db")


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with SQLite foreign-key enforcement enabled."""
    connection = sqlite3.connect(Path(db_path))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """Create the database if needed and apply the v0.3 schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection(path) as connection:
        connection.executescript(schema)

    return path


def set_app_setting(
    key: str,
    value: Any,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """JSON-encode and upsert an application setting."""
    init_db(db_path)
    value_json = json.dumps(value, ensure_ascii=False)
    updated_at = datetime.now(timezone.utc).isoformat()

    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, value_json, updated_at),
        )


def get_app_setting(
    key: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    default: Any = None,
) -> Any:
    """Return a decoded application setting, or ``default`` if absent."""
    init_db(db_path)

    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return default
    return json.loads(row[0])
