"""Load sanitized MOOCs-derived task candidates for the task list MVP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from backend.app.core.course_rules import normalize_course_code
from backend.app.core.moocs_sync.importer import normalize_course_details
from backend.app.core.task_generator import TaskPrototype


MOOCS_TASK_CAUTION = (
    "MOOCs由来の課題候補です。締切・提出場所・提出形式は抽出できた項目だけを"
    "表示し、不明な項目はunknownとして扱います。公式表示を必ず確認してください。"
)
MOOCS_TASK_SOURCE = "moocs"
SUBMISSION_FORMAT_KEYS = (
    "submission_format",
    "submission_type",
    "accepted_file_types",
    "file_types",
    "format",
)
TEXT_LIMIT = 240


def load_moocs_derived_task_prototypes(
    course_codes: list[str],
    path: Path,
) -> tuple[list[TaskPrototype], list[dict[str, str]]]:
    """Load MOOCs-derived task prototypes from an optional sanitized JSON file."""
    if not path.exists():
        return [], []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = normalize_course_details(payload)
    except Exception as exc:
        return [], [{"message": f"Could not load MOOCs-derived task candidates: {exc}"}]

    selected_codes = {normalize_course_code(code) for code in course_codes}
    courses_by_id = {course["id"]: course for course in records["courses"]}
    lectures_by_id = {lecture["id"]: lecture for lecture in records["lectures"]}
    pages_by_id = {page["id"]: page for page in records["pages"]}

    tasks: list[TaskPrototype] = []
    for record in records["tasks"]:
        course = courses_by_id.get(record["course_id"], {})
        course_code = normalize_course_code(course.get("course_code") or "")
        if course_code not in selected_codes:
            continue

        lecture = lectures_by_id.get(record.get("lecture_id"), {})
        page = pages_by_id.get(record.get("page_id"), {})
        raw = record.get("raw_json") if isinstance(record.get("raw_json"), Mapping) else {}
        meta = raw.get("_aio_task_meta") if isinstance(raw, Mapping) else {}
        if not isinstance(meta, Mapping):
            meta = {}

        tasks.append(
            TaskPrototype(
                task_id=moocs_task_id(course_code, record["id"]),
                course_code=course_code,
                title=str(record.get("title") or "MOOCs task").strip(),
                source=MOOCS_TASK_SOURCE,
                deadline_rule=deadline_rule(record),
                submission_channel=submission_channel(meta),
                confidence=confidence(meta),
                description=description_text(record, meta),
                deadline_note=deadline_note(record, meta),
                submission_note=submission_note(meta),
                caution_note=MOOCS_TASK_CAUTION,
                kind=f"moocs_{task_kind(meta)}",
                course_title=nullable_text(course.get("title")),
                lecture_key=lecture_key(lecture),
                lecture_title=nullable_text(lecture.get("title")),
                deadline_confidence=deadline_confidence(record, meta),
                submission_confidence=submission_confidence(meta),
                submission_format_text=submission_format_text(raw),
                submission_format_confidence=submission_format_confidence(raw),
                evidence_type=MOOCS_TASK_SOURCE,
                evidence_label=evidence_label(record, page),
                evidence_source=nullable_text(record.get("moocs_url") or page.get("moocs_url")),
            )
        )

    return tasks, []


def moocs_task_id(course_code: str, normalized_task_id: Any) -> str:
    suffix = str(normalized_task_id or "").strip()
    if suffix.startswith("task:"):
        suffix = suffix.split(":", 1)[1]
    return f"moocs-task:{normalize_course_code(course_code)}:{suffix}"


def deadline_rule(record: Mapping[str, Any]) -> str:
    return "moocs_explicit" if record.get("deadline_at") else "unknown"


def deadline_note(record: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    deadline_at = nullable_text(record.get("deadline_at"))
    if deadline_at:
        return f"MOOCs explicit deadline_at: {deadline_at}"
    candidates = text_list(meta.get("deadline_text_candidates"))
    if candidates:
        return f"MOOCs deadline text candidate: {candidates[0]}"
    return "unknown"


def deadline_confidence(record: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    if record.get("deadline_at"):
        return "high"
    if text_list(meta.get("deadline_text_candidates")):
        return "low"
    return "unknown"


def submission_channel(meta: Mapping[str, Any]) -> str:
    channel = nullable_text(meta.get("submit_channel_candidate"))
    return channel or "unknown"


def submission_note(meta: Mapping[str, Any]) -> str:
    if meta.get("submit_channel_candidate") == "moocs":
        reason = nullable_text(meta.get("submit_channel_reason"))
        return reason or "MOOCs submit channel detected"
    return "unknown"


def submission_confidence(meta: Mapping[str, Any]) -> str:
    return nullable_text(meta.get("submit_channel_confidence")) or "unknown"


def submission_format_text(raw: Mapping[str, Any]) -> str:
    value = find_value_by_keys(raw, SUBMISSION_FORMAT_KEYS)
    if value in (None, ""):
        return "unknown"
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value).strip()
    return limited_text(text) or "unknown"


def submission_format_confidence(raw: Mapping[str, Any]) -> str:
    value = find_value_by_keys(raw, SUBMISSION_FORMAT_KEYS)
    return "medium" if value not in (None, "") else "unknown"


def description_text(record: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    description = nullable_text(record.get("description"))
    if description:
        return limited_text(description)
    contexts = text_list(meta.get("html_keyword_contexts"))
    if contexts:
        return limited_text(contexts[0])
    return "MOOCs-derived task candidate. Confirm details on the official MOOCs page."


def evidence_label(record: Mapping[str, Any], page: Mapping[str, Any]) -> str:
    return (
        nullable_text(page.get("title"))
        or nullable_text(record.get("title"))
        or "MOOCs task page"
    )


def task_kind(meta: Mapping[str, Any]) -> str:
    kind = nullable_text(meta.get("kind"))
    return kind or "candidate"


def confidence(meta: Mapping[str, Any]) -> str:
    return nullable_text(meta.get("confidence")) or "low"


def lecture_key(lecture: Mapping[str, Any]) -> str | None:
    number = lecture.get("lecture_number")
    if isinstance(number, int):
        return f"{number:02d}"
    return nullable_text(number)


def find_value_by_keys(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            if value.get(key) not in (None, ""):
                return value[key]
        for item in value.values():
            found = find_value_by_keys(item, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_value_by_keys(item, keys)
            if found not in (None, ""):
                return found
    return None


def text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [limited_text(item) for item in value if limited_text(item)]


def nullable_text(value: Any) -> str | None:
    text = limited_text(value)
    return text or None


def limited_text(value: Any, limit: int = TEXT_LIMIT) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
