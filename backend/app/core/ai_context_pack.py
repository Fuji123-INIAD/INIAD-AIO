"""AI-ready context packs combining task candidates and material snippets."""

from __future__ import annotations

from typing import Any

from backend.app.core.context_pack import MATERIAL_SEARCH_CAUTION
from backend.app.core.task_backlog import TASK_BACKLOG_CAUTION


AI_CONTEXT_INSTRUCTIONS = (
    "Use only the task and material facts present in this tool result. "
    "Do not infer official deadlines, submission locations, submission formats, "
    "grading conditions, or full lecture coverage beyond the provided fields."
)
AI_CONTEXT_CAUTION = (
    "AIO is a local context provider, not the official course source. "
    "MOOCs or other official course pages remain authoritative."
)
DEFAULT_SNIPPET_CHARS = 360
MAX_SNIPPET_CHARS = 1200


def build_ai_ready_context_pack(
    *,
    query: str,
    task_payload: dict[str, Any],
    material_payload: dict[str, Any],
    filters: dict[str, Any] | None = None,
    task_limit: int = 8,
    snippet_chars: int = DEFAULT_SNIPPET_CHARS,
) -> dict[str, Any]:
    """Return a compact context pack designed for downstream chat AI use."""
    normalized_task_limit = max(1, min(int(task_limit or 8), 20))
    normalized_snippet_chars = max(120, min(int(snippet_chars or DEFAULT_SNIPPET_CHARS), MAX_SNIPPET_CHARS))
    raw_tasks = [
        item
        for item in task_payload.get("items", [])
        if isinstance(item, dict)
    ][:normalized_task_limit]
    raw_materials = [
        item
        for item in material_payload.get("items", [])
        if isinstance(item, dict)
    ]
    rule_tasks, moocs_tasks, other_tasks = split_tasks(raw_tasks)
    text_snippets, metadata_only = split_materials(raw_materials)

    return {
        "status": "ok",
        "pack_type": "ai_ready_task_material_context",
        "query": query,
        "filters": compact_dict(filters or {}),
        "summary": pack_summary(query, raw_tasks, text_snippets, metadata_only),
        "instructions": AI_CONTEXT_INSTRUCTIONS,
        "tasks": {
            "summary": task_payload.get("summary"),
            "count": len(raw_tasks),
            "rule_based": [task_context_item(item) for item in rule_tasks],
            "moocs_derived": [task_context_item(item) for item in moocs_tasks],
            "other": [task_context_item(item) for item in other_tasks],
            "caution": task_payload.get("caution") or TASK_BACKLOG_CAUTION,
        },
        "materials": {
            "summary": material_payload.get("summary"),
            "query": material_payload.get("query") or query,
            "mode": material_payload.get("mode"),
            "text_snippets": [
                material_context_item(item, max_chars=normalized_snippet_chars)
                for item in text_snippets
            ],
            "metadata_only": [
                material_context_item(item, max_chars=normalized_snippet_chars)
                for item in metadata_only
            ],
            "counts": {
                "total": len(raw_materials),
                "text_snippets": len(text_snippets),
                "metadata_only": len(metadata_only),
            },
            "caution": material_payload.get("caution") or MATERIAL_SEARCH_CAUTION,
        },
        "cautions": [
            AI_CONTEXT_CAUTION,
            task_payload.get("caution") or TASK_BACKLOG_CAUTION,
            material_payload.get("caution") or MATERIAL_SEARCH_CAUTION,
        ],
        "warnings": [
            *safe_warning_list(task_payload.get("warnings")),
            *safe_warning_list(material_payload.get("warnings")),
        ],
    }


def split_tasks(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rule_based: list[dict[str, Any]] = []
    moocs_derived: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for item in items:
        source = text(item.get("source"))
        source_kind = text(item.get("source_kind"))
        kind = text(item.get("kind"))
        if source == "course_rule" or source_kind == "course_rule":
            rule_based.append(item)
        elif source == "moocs" or source_kind == "moocs" or kind.startswith("moocs_"):
            moocs_derived.append(item)
        else:
            other.append(item)
    return rule_based, moocs_derived, other


def split_materials(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text_items: list[dict[str, Any]] = []
    metadata_items: list[dict[str, Any]] = []
    for item in items:
        if is_metadata_only(item):
            metadata_items.append(item)
        else:
            text_items.append(item)
    return text_items, metadata_items


def task_context_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": item.get("task_id") or item.get("id"),
        "course_code": item.get("course_code"),
        "course_title": item.get("course_title") or item.get("display_course_name"),
        "title": item.get("title"),
        "description": limited_text(item.get("description"), 280),
        "source": item.get("source"),
        "source_kind": item.get("source_kind"),
        "kind": item.get("kind"),
        "confidence": item.get("confidence"),
        "status": item.get("status"),
        "active": item.get("active"),
        "deadline_text": item.get("deadline_text"),
        "deadline_confidence": item.get("deadline_confidence"),
        "submission_text": item.get("submission_text"),
        "submission_confidence": item.get("submission_confidence"),
        "submission_format_text": item.get("submission_format_text"),
        "submission_format_confidence": item.get("submission_format_confidence"),
        "open_url": item.get("primary_action_url"),
        "evidence_summary": item.get("evidence_summary"),
        "evidence_url": item.get("evidence_url"),
        "caution": item.get("caution"),
    }


def material_context_item(item: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    metadata_only = is_metadata_only(item)
    return {
        "material_id": item.get("material_id"),
        "chunk_id": item.get("chunk_id"),
        "course_code": item.get("course_code"),
        "course_title": item.get("course_title"),
        "lecture_key": item.get("lecture_key"),
        "lecture_title": item.get("lecture_title"),
        "title": item.get("title"),
        "source_label": item.get("source_label"),
        "source_kind": material_source_kind(item),
        "provider": item.get("provider"),
        "source_type": item.get("source_type"),
        "extraction_method": item.get("extraction_method"),
        "chunk_type": item.get("chunk_type"),
        "metadata_only": metadata_only,
        "text_available": item.get("text_available"),
        "confidence": "low" if metadata_only else "medium",
        "score": item.get("score"),
        "open_url": item.get("open_url"),
        "snippet": limited_text(item.get("excerpt") or item.get("text"), max_chars),
        "warnings": safe_warning_list(item.get("warnings")),
    }


def material_source_kind(item: dict[str, Any]) -> str:
    provider = text(item.get("provider"))
    source_type = text(item.get("source_type"))
    if "moocs_collect" in provider or "moocs_collect" in source_type:
        return "moocs_collect"
    if "moocs" in provider or "moocs" in source_type:
        return "moocs"
    if "pdf" in provider or "pdf" in source_type:
        return "filesystem"
    return "unknown"


def is_metadata_only(item: dict[str, Any]) -> bool:
    return (
        item.get("chunk_type") == "metadata"
        or item.get("text_available") is False
        or item.get("extraction_method") == "metadata_only"
    )


def pack_summary(
    query: str,
    tasks: list[dict[str, Any]],
    text_snippets: list[dict[str, Any]],
    metadata_only: list[dict[str, Any]],
) -> str:
    return (
        f"AI-ready context for '{query}': "
        f"{len(tasks)} pending task candidates, "
        f"{len(text_snippets)} text snippets, "
        f"{len(metadata_only)} metadata-only fallback entries."
    )


def safe_warning_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and str(item).strip() != ""
    }


def limited_text(value: Any, max_chars: int) -> str:
    value_text = " ".join(str(value or "").split())
    limit = max(20, int(max_chars))
    if len(value_text) <= limit:
        return value_text
    return value_text[: limit - 3].rstrip() + "..."


def text(value: Any) -> str:
    return str(value or "").strip().casefold()
