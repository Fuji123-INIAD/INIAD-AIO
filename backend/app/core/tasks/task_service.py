"""Queries and user-state updates for local MOOCs tasks."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.db.local_db import DEFAULT_DB_PATH, get_connection, init_db


ALLOWED_TASK_STATUSES = frozenset({"open", "done", "ignored"})


class TaskNotFoundError(ValueError):
    """Raised when a task status update targets an unknown task."""


def _resolve_db_path(db_path: str | Path | None) -> str | Path:
    return DEFAULT_DB_PATH if db_path is None else db_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_now(now: str | datetime | None) -> str:
    if now is None:
        return _utc_now_iso()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc).isoformat()
    return now


def list_active_tasks(
    db_path: str | Path | None = None,
    now: str | datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return open future tasks and open tasks with no known deadline."""
    resolved_db_path = _resolve_db_path(db_path)
    init_db(resolved_db_path)
    now_iso = _normalize_now(now)

    query = """
        SELECT
            tasks.id,
            tasks.course_id,
            tasks.lecture_id,
            tasks.page_id,
            tasks.title,
            tasks.description,
            tasks.deadline_at,
            tasks.moocs_url,
            COALESCE(user_task_status.status, 'open') AS status
        FROM tasks
        LEFT JOIN user_task_status
            ON user_task_status.task_id = tasks.id
        WHERE
            (
                NOT EXISTS (SELECT 1 FROM user_course_settings)
                OR EXISTS (
                    SELECT 1
                    FROM user_course_settings
                    WHERE user_course_settings.course_id = tasks.course_id
                      AND user_course_settings.enabled = 1
                )
            )
            AND COALESCE(user_task_status.status, 'open') = 'open'
            AND (
                tasks.deadline_at IS NULL
                OR julianday(tasks.deadline_at) > julianday(?)
            )
        ORDER BY
            CASE WHEN tasks.deadline_at IS NULL THEN 1 ELSE 0 END,
            julianday(tasks.deadline_at) ASC,
            tasks.title ASC
    """

    with get_connection(resolved_db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, (now_iso,)).fetchall()

    result: dict[str, list[dict[str, Any]]] = {
        "upcoming": [],
        "unknown_deadline": [],
    }
    for row in rows:
        task = dict(row)
        bucket = "unknown_deadline" if task["deadline_at"] is None else "upcoming"
        result[bucket].append(task)

    return result


def set_task_status(
    task_id: str,
    status: str,
    db_path: str | Path | None = None,
) -> None:
    """Set a task's user status, raising if the status or task is invalid."""
    if status not in ALLOWED_TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")

    resolved_db_path = _resolve_db_path(db_path)
    init_db(resolved_db_path)
    updated_at = _utc_now_iso()
    checked_done_at = updated_at if status == "done" else None

    with get_connection(resolved_db_path) as connection:
        task_exists = connection.execute(
            "SELECT 1 FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if task_exists is None:
            raise TaskNotFoundError(f"Task not found: {task_id}")

        connection.execute(
            """
            INSERT INTO user_task_status (
                task_id, status, checked_done_at, updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status = excluded.status,
                checked_done_at = excluded.checked_done_at,
                updated_at = excluded.updated_at
            """,
            (task_id, status, checked_done_at, updated_at),
        )
