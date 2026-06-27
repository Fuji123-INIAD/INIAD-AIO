"""In-memory user status model for generated task prototypes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


ALLOWED_USER_TASK_STATUSES = frozenset({"todo", "done", "ignored"})


@dataclass(frozen=True)
class UserTaskStatus:
    task_id: str
    status: str
    updated_at: datetime | None = None
    checked_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_USER_TASK_STATUSES:
            raise ValueError(f"Invalid user task status: {self.status}")
        if self.status != "done" and self.checked_at is not None:
            raise ValueError("checked_at is only allowed for done status")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_default_status(
    task_id: str, *, now: datetime | None = None
) -> UserTaskStatus:
    timestamp = now or _now()
    return UserTaskStatus(task_id=task_id, status="todo", updated_at=timestamp)


def mark_done(
    status: UserTaskStatus, *, now: datetime | None = None
) -> UserTaskStatus:
    timestamp = now or _now()
    return UserTaskStatus(
        task_id=status.task_id,
        status="done",
        updated_at=timestamp,
        checked_at=timestamp,
    )


def mark_todo(
    status: UserTaskStatus, *, now: datetime | None = None
) -> UserTaskStatus:
    timestamp = now or _now()
    return UserTaskStatus(task_id=status.task_id, status="todo", updated_at=timestamp)


def mark_ignored(
    status: UserTaskStatus, *, now: datetime | None = None
) -> UserTaskStatus:
    timestamp = now or _now()
    return UserTaskStatus(
        task_id=status.task_id,
        status="ignored",
        updated_at=timestamp,
    )


def is_active(status: UserTaskStatus) -> bool:
    return status.status == "todo"
