"""Static course rule registry for v0.3 task generation experiments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CourseRule:
    course_code: str
    deadline_rule: str
    submission_channel: str
    confidence: str
    notes: str


_COURSE_RULES: dict[str, CourseRule] = {
    "COT101": CourseRule(
        course_code="COT101",
        deadline_rule="next_lecture_previous_day",
        submission_channel="moocs",
        confidence="medium",
        notes=(
            "Assignment content is commonly in Slides, and submission is usually on MOOCs. "
            "Treat the deadline as the day before the next lecture."
        ),
    ),
    "SEM101": CourseRule(
        course_code="SEM101",
        deadline_rule="same_week_sunday_2359",
        submission_channel="email_to_instructor",
        confidence="medium",
        notes=(
            "Information is mostly in Slides. Submission is commonly sent by email "
            "to the instructor."
        ),
    ),
    "COT105": CourseRule(
        course_code="COT105",
        deadline_rule="explicit_or_unknown",
        submission_channel="moocs",
        confidence="low",
        notes="Prefer explicit HTML evidence because the format varies by instructor.",
    ),
}


def normalize_course_code(course_code: str) -> str:
    return course_code.strip().upper()


def get_course_rule(course_code: str) -> CourseRule | None:
    return _COURSE_RULES.get(normalize_course_code(course_code))


def list_course_rules() -> dict[str, CourseRule]:
    return dict(_COURSE_RULES)
