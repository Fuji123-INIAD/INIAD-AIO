"""Persist normalized MOOCs metadata in the v0.3 SQLite database."""

from __future__ import annotations

import json
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.app.core.moocs_sync.importer import (
    load_course_details_json,
    normalize_course_details,
)
from backend.app.db.local_db import DEFAULT_DB_PATH, get_connection, init_db


TABLE_ORDER = ("courses", "lectures", "pages", "materials", "tasks")


def import_moocs_course_details(
    path: str | Path,
    db_path: str | Path | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Import a v0.2-style MOOCs detail JSON file into SQLite."""
    data = load_course_details_json(path)
    return import_moocs_course_details_data(data, db_path=db_path, now=now)


def import_moocs_course_details_data(
    data: Any,
    db_path: str | Path | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Normalize and atomically upsert MOOCs detail data into SQLite."""
    resolved_db_path = DEFAULT_DB_PATH if db_path is None else db_path
    timestamp = _normalize_timestamp(now)
    run_id = f"sync:{uuid.uuid4().hex}"
    init_db(resolved_db_path)

    with closing(get_connection(resolved_db_path)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO sync_runs (
                    id, sync_type, status, started_at, message, detail_json
                )
                VALUES (?, 'moocs_metadata', 'running', ?, ?, ?)
                """,
                (run_id, timestamp, "MOOCs metadata import started", "{}"),
            )

    try:
        records = normalize_course_details(data, now=timestamp)
        counts = {table: len(records[table]) for table in TABLE_ORDER}
        with closing(get_connection(resolved_db_path)) as connection:
            with connection:
                _upsert_courses(connection, records["courses"])
                _upsert_lectures(connection, records["lectures"])
                _upsert_pages(connection, records["pages"])
                _upsert_materials(connection, records["materials"])
                _upsert_tasks(connection, records["tasks"])
                connection.execute(
                    """
                    UPDATE sync_runs
                    SET status = 'ok', finished_at = ?, message = ?, detail_json = ?
                    WHERE id = ?
                    """,
                    (
                        timestamp,
                        "MOOCs metadata import completed",
                        json.dumps(counts, ensure_ascii=False, sort_keys=True),
                        run_id,
                    ),
                )
    except Exception as exc:
        finished_at = _utc_now_iso() if now is None else timestamp
        with closing(get_connection(resolved_db_path)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE sync_runs
                    SET status = 'error', finished_at = ?, message = ?, detail_json = ?
                    WHERE id = ?
                    """,
                    (
                        finished_at,
                        str(exc),
                        json.dumps({"error": str(exc)}, ensure_ascii=False),
                        run_id,
                    ),
                )
        raise

    return {"status": "ok", "run_id": run_id, "counts": counts}


def _upsert_courses(connection, records: Iterable[Mapping[str, Any]]) -> None:
    sql = """
        INSERT INTO courses (
            id, course_code, title, year, moocs_url, source, source_key,
            raw_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            course_code = excluded.course_code,
            title = excluded.title,
            year = excluded.year,
            moocs_url = excluded.moocs_url,
            source = excluded.source,
            source_key = excluded.source_key,
            raw_json = excluded.raw_json,
            updated_at = excluded.updated_at
    """
    connection.executemany(sql, (_course_values(record) for record in records))


def _upsert_lectures(connection, records: Iterable[Mapping[str, Any]]) -> None:
    sql = """
        INSERT INTO lectures (
            id, course_id, lecture_number, title, moocs_url, source_key,
            raw_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            course_id = excluded.course_id,
            lecture_number = excluded.lecture_number,
            title = excluded.title,
            moocs_url = excluded.moocs_url,
            source_key = excluded.source_key,
            raw_json = excluded.raw_json,
            updated_at = excluded.updated_at
    """
    connection.executemany(sql, (_lecture_values(record) for record in records))


def _upsert_pages(connection, records: Iterable[Mapping[str, Any]]) -> None:
    sql = """
        INSERT INTO pages (
            id, lecture_id, page_number, title, moocs_url, source_key,
            raw_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            lecture_id = excluded.lecture_id,
            page_number = excluded.page_number,
            title = excluded.title,
            moocs_url = excluded.moocs_url,
            source_key = excluded.source_key,
            raw_json = excluded.raw_json,
            updated_at = excluded.updated_at
    """
    connection.executemany(sql, (_page_values(record) for record in records))


def _upsert_materials(connection, records: Iterable[Mapping[str, Any]]) -> None:
    sql = """
        INSERT INTO materials (
            id, course_id, lecture_id, page_id, title, material_type,
            moocs_url, local_path, source_key, raw_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            course_id = excluded.course_id,
            lecture_id = excluded.lecture_id,
            page_id = excluded.page_id,
            title = excluded.title,
            material_type = excluded.material_type,
            moocs_url = excluded.moocs_url,
            local_path = excluded.local_path,
            source_key = excluded.source_key,
            raw_json = excluded.raw_json,
            updated_at = excluded.updated_at
    """
    connection.executemany(sql, (_material_values(record) for record in records))


def _upsert_tasks(connection, records: Iterable[Mapping[str, Any]]) -> None:
    sql = """
        INSERT INTO tasks (
            id, course_id, lecture_id, page_id, title, description,
            deadline_at, moocs_url, source_key, raw_json, first_seen_at,
            last_seen_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            course_id = excluded.course_id,
            lecture_id = excluded.lecture_id,
            page_id = excluded.page_id,
            title = excluded.title,
            description = excluded.description,
            deadline_at = excluded.deadline_at,
            moocs_url = excluded.moocs_url,
            source_key = excluded.source_key,
            raw_json = excluded.raw_json,
            last_seen_at = excluded.last_seen_at,
            updated_at = excluded.updated_at
    """
    connection.executemany(sql, (_task_values(record) for record in records))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _course_values(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["id"], record["course_code"], record["title"], record["year"],
        record["moocs_url"], record["source"], record["source_key"],
        _json(record["raw_json"]), record["created_at"], record["updated_at"],
    )


def _lecture_values(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["id"], record["course_id"], record["lecture_number"],
        record["title"], record["moocs_url"], record["source_key"],
        _json(record["raw_json"]), record["created_at"], record["updated_at"],
    )


def _page_values(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["id"], record["lecture_id"], record["page_number"],
        record["title"], record["moocs_url"], record["source_key"],
        _json(record["raw_json"]), record["created_at"], record["updated_at"],
    )


def _material_values(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["id"], record["course_id"], record["lecture_id"],
        record["page_id"], record["title"], record["material_type"],
        record["moocs_url"], record["local_path"], record["source_key"],
        _json(record["raw_json"]), record["created_at"], record["updated_at"],
    )


def _task_values(record: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        record["id"], record["course_id"], record["lecture_id"],
        record["page_id"], record["title"], record["description"],
        record["deadline_at"], record["moocs_url"], record["source_key"],
        _json(record["raw_json"]), record["first_seen_at"],
        record["last_seen_at"], record["updated_at"],
    )


def _normalize_timestamp(value: str | datetime | None) -> str:
    if value is None:
        return _utc_now_iso()
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("now must not be empty")
        return value.strip()
    if not isinstance(value, datetime):
        raise TypeError("now must be an ISO string, datetime, or None")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
