"""AI-ready context packs combining task candidates and material snippets."""

from __future__ import annotations

import re
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
MCP_FORMAT_MAX_CHARS = 10000
MCP_TASK_LIMIT = 8
MCP_TEXT_SNIPPET_LIMIT = 5
MCP_METADATA_ONLY_LIMIT = 3
MCP_CAUTION_LIMIT = 5
MCP_FIELD_TEXT_CHARS = 160
MCP_SNIPPET_CHARS = 240


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


def format_ai_context_pack_for_mcp(
    pack: dict[str, Any],
    *,
    max_chars: int = MCP_FORMAT_MAX_CHARS,
) -> str:
    """Return a short, sanitized Markdown summary safe for MCP stdio clients."""
    tasks = pack.get("tasks") if isinstance(pack.get("tasks"), dict) else {}
    materials = pack.get("materials") if isinstance(pack.get("materials"), dict) else {}
    task_candidates = [
        *_object_items(tasks.get("rule_based")),
        *_object_items(tasks.get("moocs_derived")),
        *_object_items(tasks.get("other")),
    ]
    text_snippets = _object_items(materials.get("text_snippets"))
    metadata_only = _object_items(materials.get("metadata_only"))
    material_counts = materials.get("counts") if isinstance(materials.get("counts"), dict) else {}

    task_count = _int_or_len(tasks.get("count"), task_candidates)
    text_count = _int_or_len(_material_count_value(material_counts, "text_snippets"), text_snippets)
    metadata_count = _int_or_len(_material_count_value(material_counts, "metadata_only"), metadata_only)

    lines = [
        "# AI-ready context pack",
        f"- query: {_clean_text(pack.get('query'), MCP_FIELD_TEXT_CHARS)}",
        f"- task candidates count: {task_count}",
        f"- text snippets count: {text_count}",
        f"- metadata-only fallback count: {metadata_count}",
    ]

    summary = _clean_text(pack.get("summary"), 280)
    if summary:
        lines.append(f"- summary: {summary}")

    lines.extend(["", "## 課題候補"])
    if not task_candidates:
        lines.append("- none")
    for index, item in enumerate(task_candidates[:MCP_TASK_LIMIT], start=1):
        lines.extend(
            [
                f"{index}. title: {_clean_text(item.get('title'), MCP_FIELD_TEXT_CHARS)}",
                f"   course_title: {_clean_text(item.get('course_title'), MCP_FIELD_TEXT_CHARS)}",
                f"   confidence: {_clean_text(item.get('confidence'), 80)}",
                f"   caution: {_clean_text(item.get('caution') or tasks.get('caution'), 220)}",
            ]
        )

    lines.extend(["", "## 講義資料snippet"])
    if not text_snippets:
        lines.append("- none")
    for index, item in enumerate(text_snippets[:MCP_TEXT_SNIPPET_LIMIT], start=1):
        lines.extend(
            [
                f"{index}. title: {_clean_text(item.get('title') or item.get('source_label'), MCP_FIELD_TEXT_CHARS)}",
                f"   course_title: {_clean_text(item.get('course_title'), MCP_FIELD_TEXT_CHARS)}",
                f"   lecture_title: {_clean_text(item.get('lecture_title'), MCP_FIELD_TEXT_CHARS)}",
                f"   provider: {_clean_text(item.get('provider'), 120)}",
                f"   source_type: {_clean_text(item.get('source_type'), 120)}",
                f"   extraction_method: {_clean_text(item.get('extraction_method'), 120)}",
                f"   confidence: {_clean_text(item.get('confidence'), 80)}",
                f"   snippet: {_clean_text(item.get('snippet'), MCP_SNIPPET_CHARS)}",
            ]
        )

    lines.extend(["", "## metadata-only fallback"])
    if not metadata_only:
        lines.append("- none")
    for index, item in enumerate(metadata_only[:MCP_METADATA_ONLY_LIMIT], start=1):
        warning = _warning_or_caution(item, materials.get("caution"))
        lines.extend(
            [
                f"{index}. title: {_clean_text(item.get('title') or item.get('source_label'), MCP_FIELD_TEXT_CHARS)}",
                f"   provider: {_clean_text(item.get('provider'), 120)}",
                f"   extraction_method: {_clean_text(item.get('extraction_method'), 120)}",
                f"   text_available: {_clean_text(item.get('text_available'), 40)}",
                f"   warning/caution: {warning}",
            ]
        )

    lines.extend(["", "## cautions"])
    cautions = _pack_cautions(pack, tasks, materials)
    if not cautions:
        lines.append("- caution: none")
    for caution in cautions[:MCP_CAUTION_LIMIT]:
        lines.append(f"- caution: {caution}")

    return _limit_mcp_output("\n".join(lines), max_chars)


def summarize_ai_context_pack_for_mcp(
    pack: dict[str, Any],
    rendered_text: str,
) -> dict[str, Any]:
    """Return small structured metadata for MCP without embedding the full pack."""
    tasks = pack.get("tasks") if isinstance(pack.get("tasks"), dict) else {}
    materials = pack.get("materials") if isinstance(pack.get("materials"), dict) else {}
    task_candidates = [
        *_object_items(tasks.get("rule_based")),
        *_object_items(tasks.get("moocs_derived")),
        *_object_items(tasks.get("other")),
    ]
    text_snippets = _object_items(materials.get("text_snippets"))
    metadata_only = _object_items(materials.get("metadata_only"))
    material_counts = materials.get("counts") if isinstance(materials.get("counts"), dict) else {}

    return {
        "status": pack.get("status") or "ok",
        "pack_type": pack.get("pack_type"),
        "query": pack.get("query"),
        "format": "compact_markdown",
        "text_length": len(rendered_text),
        "counts": {
            "tasks": _int_or_len(tasks.get("count"), task_candidates),
            "text_snippets": _int_or_len(_material_count_value(material_counts, "text_snippets"), text_snippets),
            "metadata_only": _int_or_len(_material_count_value(material_counts, "metadata_only"), metadata_only),
        },
        "caution": AI_CONTEXT_CAUTION,
    }


def _material_count_value(counts: dict[str, Any], key: str) -> Any:
    return counts.get(key)


def _object_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int_or_len(value: Any, fallback_items: list[dict[str, Any]]) -> int:
    if isinstance(value, int):
        return value
    return len(fallback_items)


def _clean_text(value: object, limit: int = MCP_SNIPPET_CHARS) -> str:
    if value is None:
        return ""
    text_value = str(value).replace("\x00", "")
    text_value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text_value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    normalized_limit = max(1, int(limit))
    if len(text_value) > normalized_limit:
        if normalized_limit <= 3:
            return text_value[:normalized_limit]
        return text_value[: normalized_limit - 3].rstrip() + "..."
    return text_value


def _warning_or_caution(item: dict[str, Any], fallback_caution: Any) -> str:
    values: list[str] = []
    for key in ("warning", "caution"):
        value = _clean_text(item.get(key), 220)
        if value:
            values.append(value)
    warnings = item.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings[:2]:
            values.append(_warning_text(warning))
    if not values:
        fallback = _clean_text(fallback_caution, 220)
        if fallback:
            values.append(fallback)
    return _clean_text("; ".join(value for value in values if value), 260)


def _warning_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("message", "warning", "detail", "caution", "reason"):
            text_value = _clean_text(value.get(key), 180)
            if text_value:
                return text_value
    return _clean_text(value, 180)


def _pack_cautions(
    pack: dict[str, Any],
    tasks: dict[str, Any],
    materials: dict[str, Any],
) -> list[str]:
    values: list[str] = []
    raw_cautions = pack.get("cautions")
    if isinstance(raw_cautions, list):
        values.extend(_clean_text(item, 260) for item in raw_cautions)
    values.extend(
        [
            _clean_text(tasks.get("caution"), 260),
            _clean_text(materials.get("caution"), 260),
        ]
    )
    warnings = pack.get("warnings")
    if isinstance(warnings, list):
        values.extend(_warning_text(item) for item in warnings)

    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _limit_mcp_output(text_value: str, max_chars: int) -> str:
    text_value = text_value.replace("\x00", "")
    text_value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text_value)
    normalized_limit = max(2000, int(max_chars))
    if len(text_value) <= normalized_limit:
        return text_value
    suffix = "\n\n[truncated: MCP response length limit]"
    return text_value[: normalized_limit - len(suffix)].rstrip() + suffix


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
