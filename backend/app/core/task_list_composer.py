"""Compose display-ready task list items from prototypes and user statuses."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.task_generator import TaskPrototype
from backend.app.core.user_task_status import (
    UserTaskStatus,
    create_default_status,
    is_active,
)


MAX_EVIDENCE_PER_ITEM = 5
EVIDENCE_TYPE_ORDER = {
    "course_rule": 0,
    "html": 1,
    "slides": 2,
}
EVIDENCE_CONFIDENCE_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}


@dataclass(frozen=True)
class TaskEvidence:
    type: str
    label: str
    source: str
    confidence: str


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
    display_course_name: str
    short_name: str
    track: str
    evidence: list[TaskEvidence]
    evidence_omitted_count: int


def compose_task_list_items(
    tasks: list[TaskPrototype],
    statuses: dict[str, UserTaskStatus] | None = None,
    extra_evidence: dict[str, list[TaskEvidence]] | None = None,
) -> list[TaskListItem]:
    statuses = statuses or {}
    extra_evidence = extra_evidence or {}

    items: list[TaskListItem] = []
    for task in tasks:
        status = statuses.get(task.task_id) or create_default_status(task.task_id)
        evidence, evidence_omitted_count = prepare_evidence(
            course_rule_evidence(task) + evidence_for_task(task, extra_evidence)
        )
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
                display_course_name=display_course_name(task.course_code),
                short_name=short_name(task.course_code),
                track=track(task.course_code),
                evidence=evidence,
                evidence_omitted_count=evidence_omitted_count,
            )
        )
    return items


def course_rule_evidence(task: TaskPrototype) -> list[TaskEvidence]:
    return [
        TaskEvidence(
            type="course_rule",
            label=f"{task.course_code} course rule",
            source=task.source,
            confidence=task.confidence,
        )
    ]


def evidence_for_task(
    task: TaskPrototype,
    extra_evidence: dict[str, list[TaskEvidence]],
) -> list[TaskEvidence]:
    return [
        *extra_evidence.get(task.task_id, []),
        *extra_evidence.get(task.course_code, []),
    ]


def prepare_evidence(
    evidence_items: list[TaskEvidence],
    *,
    limit: int = MAX_EVIDENCE_PER_ITEM,
) -> tuple[list[TaskEvidence], int]:
    deduped_by_key: dict[tuple[str, str], tuple[int, TaskEvidence]] = {}
    duplicate_count = 0

    for index, evidence in enumerate(evidence_items):
        key = (evidence.type, evidence.source)
        existing = deduped_by_key.get(key)
        if existing is None:
            deduped_by_key[key] = (index, evidence)
            continue

        duplicate_count += 1
        existing_index, existing_evidence = existing
        if confidence_rank(evidence.confidence) < confidence_rank(
            existing_evidence.confidence
        ):
            deduped_by_key[key] = (existing_index, evidence)

    ranked_evidence = [
        indexed_evidence
        for indexed_evidence in deduped_by_key.values()
    ]
    ranked_evidence.sort(
        key=lambda item: (
            type_rank(item[1].type),
            confidence_rank(item[1].confidence),
            item[0],
        )
    )

    limited = [evidence for _, evidence in ranked_evidence[:limit]]
    omitted_count = duplicate_count + max(0, len(ranked_evidence) - limit)
    return limited, omitted_count


def type_rank(evidence_type: str) -> int:
    return EVIDENCE_TYPE_ORDER.get(evidence_type, len(EVIDENCE_TYPE_ORDER))


def confidence_rank(confidence: str) -> int:
    return EVIDENCE_CONFIDENCE_ORDER.get(
        confidence,
        len(EVIDENCE_CONFIDENCE_ORDER),
    )


def display_course_name(course_code: str) -> str:
    return course_code


def short_name(course_code: str) -> str:
    return course_code


def track(course_code: str) -> str:
    return "".join(char for char in course_code if char.isalpha())
