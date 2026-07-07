"""Generate task prototypes from static course rules."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.course_rules import get_course_rule


@dataclass(frozen=True)
class TaskPrototype:
    task_id: str
    course_code: str
    title: str
    source: str
    deadline_rule: str
    submission_channel: str
    confidence: str
    description: str
    deadline_note: str
    submission_note: str
    caution_note: str
    kind: str = "rule_based_candidate"
    course_title: str | None = None
    lecture_key: str | None = None
    lecture_title: str | None = None
    deadline_confidence: str | None = None
    submission_confidence: str | None = None
    submission_format_text: str | None = None
    submission_format_confidence: str | None = None
    evidence_type: str | None = None
    evidence_label: str | None = None
    evidence_source: str | None = None


def generate_course_rule_tasks(course_code: str) -> list[TaskPrototype]:
    rule = get_course_rule(course_code)
    if rule is None:
        return []

    return [
        TaskPrototype(
            task_id=f"course-rule:{rule.course_code}",
            course_code=rule.course_code,
            title=f"{rule.course_code} 課題",
            source="course_rule",
            deadline_rule=rule.deadline_rule,
            submission_channel=rule.submission_channel,
            confidence=rule.confidence,
            description=rule.description,
            deadline_note=rule.deadline_note,
            submission_note=rule.submission_note,
            caution_note=rule.caution_note,
        )
    ]
