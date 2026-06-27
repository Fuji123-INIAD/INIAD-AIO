"""Compose display-ready task list items from prototypes and user statuses."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.task_generator import TaskPrototype
from backend.app.core.user_task_status import (
    UserTaskStatus,
    create_default_status,
    is_active,
)


@dataclass(frozen=True)
class TaskListItem:
    task_id: str
    course_code: str
    title: str
    source: str
    status: str
    active: bool
    deadline_rule: str
    submission_channel: str
    confidence: str


def compose_task_list_items(
    tasks: list[TaskPrototype],
    statuses: dict[str, UserTaskStatus] | None = None,
) -> list[TaskListItem]:
    statuses = statuses or {}

    items: list[TaskListItem] = []
    for task in tasks:
        status = statuses.get(task.task_id) or create_default_status(task.task_id)
        items.append(
            TaskListItem(
                task_id=task.task_id,
                course_code=task.course_code,
                title=task.title,
                source=task.source,
                status=status.status,
                active=is_active(status),
                deadline_rule=task.deadline_rule,
                submission_channel=task.submission_channel,
                confidence=task.confidence,
            )
        )
    return items
