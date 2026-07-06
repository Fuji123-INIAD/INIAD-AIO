"""Claude-safe task backlog payloads built from AIO task list items."""

from __future__ import annotations

from typing import Any


TASK_BACKLOG_CAUTION = (
    "この一覧はAIOが検出した課題候補です。実際の締切・提出場所・提出形式は"
    "MOOCs等の公式表示を優先してください。tool resultに存在しない締切、"
    "提出方法、提出先、評価条件は推測で補完しないでください。"
)

DONE_STATUSES = frozenset({"done", "ignored", "hidden"})
PENDING_STATUSES = frozenset({"todo", "needs_check", "active", "pending"})


def build_pending_tasks_payload(task_payload: dict[str, Any]) -> dict[str, Any]:
    """Return pending task candidates from an existing /api/tasks-style payload."""
    raw_items = task_payload.get("items") or task_payload.get("tasks") or []
    items = [
        pending_task_item(item)
        for item in raw_items
        if isinstance(item, dict) and should_include_pending_task(item)
    ]
    summary = summarize_pending_items(items)
    return {
        "status": "ok",
        "summary": summary,
        "count": len(items),
        "items": items,
        "caution": TASK_BACKLOG_CAUTION,
        "warnings": task_payload.get("warnings") or [],
    }


def summarize_task_backlog_payload(task_payload: dict[str, Any]) -> dict[str, Any]:
    pending = build_pending_tasks_payload(task_payload)
    return {
        "status": pending["status"],
        "summary": pending["summary"],
        "count": pending["count"],
        "caution": pending["caution"],
        "items": pending["items"][:5],
        "warnings": pending["warnings"],
    }


def should_include_pending_task(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    if status in DONE_STATUSES:
        return False
    if item.get("active") is False and status not in PENDING_STATUSES:
        return False
    return True


def pending_task_item(item: dict[str, Any]) -> dict[str, Any]:
    deadline_text = first_text(
        item.get("deadline_text"),
        item.get("deadline_note"),
        item.get("deadline_rule"),
    )
    submission_text = first_text(
        item.get("submission_text"),
        item.get("submission_note"),
        item.get("submission_channel"),
    )
    evidence_items = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    evidence_summary = summarize_evidence(evidence_items)
    caution = first_text(item.get("caution"), item.get("caution_note")) or TASK_BACKLOG_CAUTION
    return {
        "task_id": first_text(item.get("task_id"), item.get("id")),
        "course_code": nullable_text(item.get("course_code")),
        "course_title": nullable_text(item.get("course_title")),
        "display_course_name": nullable_text(item.get("display_course_name")),
        "title": nullable_text(item.get("title")),
        "description": nullable_text(item.get("description")),
        "status": nullable_text(item.get("status")) or "unknown",
        "active": bool(item.get("active", True)),
        "kind": first_text(item.get("resource_kind"), item.get("kind")) or "assignment",
        "deadline_text": deadline_text or "unknown",
        "deadline_confidence": first_text(item.get("deadline_confidence"), item.get("confidence")) or "unknown",
        "submission_text": submission_text or "unknown",
        "submission_confidence": first_text(item.get("submission_confidence"), item.get("confidence")) or "unknown",
        "primary_action_url": nullable_text(item.get("primary_action_url")),
        "evidence_summary": evidence_summary,
        "evidence_url": nullable_text(item.get("evidence_detail_url")),
        "caution": caution,
    }


def summarize_pending_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            "現在AIO上で確認が必要な課題候補は0件です。"
            "ただし、実際の課題有無はMOOCs等の公式表示を確認してください。"
        )

    course_names = []
    for item in items:
        name = first_text(
            item.get("display_course_name"),
            item.get("course_title"),
            item.get("course_code"),
        )
        if name and name not in course_names:
            course_names.append(name)

    course_phrase = "、".join(course_names[:3])
    if len(course_names) > 3:
        course_phrase += f" ほか{len(course_names) - 3}件"
    return (
        f"現在AIO上で確認が必要な課題候補は{len(items)}件です。"
        f"{course_phrase}について、MOOCsの課題ページや授業資料を確認してください。"
        "なお、実際の締切・提出場所・提出形式はMOOCs上の表示を優先してください。"
    )


def summarize_evidence(evidence_items: list[Any]) -> str:
    labels = []
    for evidence in evidence_items:
        if not isinstance(evidence, dict):
            continue
        label = first_text(evidence.get("label"), evidence.get("type"))
        confidence = first_text(evidence.get("confidence"))
        if not label:
            continue
        labels.append(f"{label} ({confidence or 'confidence unknown'})")
    return " / ".join(labels[:3]) if labels else "unknown"


def nullable_text(value: Any) -> str | None:
    text = first_text(value)
    return text or None


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
