"""JSON persistence helpers for generated task user statuses."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.user_task_status import (
    ALLOWED_USER_TASK_STATUSES,
    UserTaskStatus,
)


def load_user_task_statuses(
    path: Path,
) -> tuple[dict[str, UserTaskStatus], list[dict[str, str]]]:
    if not path.exists():
        return {}, []

    try:
        raw_statuses = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [_warning(None, f"Could not load user task status JSON: {exc}")]

    if not isinstance(raw_statuses, dict):
        return {}, [_warning(None, "User task status JSON must be an object.")]

    statuses: dict[str, UserTaskStatus] = {}
    warnings: list[dict[str, str]] = []
    for task_id, status in raw_statuses.items():
        if not isinstance(task_id, str) or not isinstance(status, str):
            warnings.append(_warning(None, "Skipped invalid user task status entry."))
            continue

        normalized_status = status.strip().lower()
        if normalized_status not in ALLOWED_USER_TASK_STATUSES:
            warnings.append(_warning(task_id, "Skipped invalid user task status."))
            continue

        statuses[task_id] = UserTaskStatus(task_id=task_id, status=normalized_status)

    return statuses, warnings


def save_user_task_statuses(
    path: Path,
    statuses: dict[str, UserTaskStatus],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        task_id: status.status
        for task_id, status in sorted(statuses.items())
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _warning(task_id: str | None, message: str) -> dict[str, str]:
    warning = {"message": message}
    if task_id is not None:
        warning["task_id"] = task_id
    return warning
