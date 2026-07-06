"""Small ontology helpers for local AIO resources and tasks."""

from __future__ import annotations

from typing import Iterable


RESOURCE_KIND_MATERIAL = "material"
RESOURCE_KIND_ASSIGNMENT = "assignment"
RESOURCE_KIND_REPORT = "report"
RESOURCE_KIND_GUIDE = "guide"
RESOURCE_KIND_UNKNOWN = "unknown"

ENTITY_TYPE_RESOURCE = "resource"
ENTITY_TYPE_TASK = "task"
ENTITY_TYPE_COURSE = "course"
ENTITY_TYPE_LECTURE = "lecture"

SOURCE_KIND_FILESYSTEM = "filesystem"
SOURCE_KIND_MOOCS_COLLECT = "moocs_collect"
SOURCE_KIND_COURSE_RULE = "course_rule"
SOURCE_KIND_HTML = "html"
SOURCE_KIND_SLIDES = "slides"

RESOURCE_KINDS = frozenset(
    {
        RESOURCE_KIND_MATERIAL,
        RESOURCE_KIND_ASSIGNMENT,
        RESOURCE_KIND_REPORT,
        RESOURCE_KIND_GUIDE,
        RESOURCE_KIND_UNKNOWN,
    }
)
SOURCE_KINDS = frozenset(
    {
        SOURCE_KIND_FILESYSTEM,
        SOURCE_KIND_MOOCS_COLLECT,
        SOURCE_KIND_COURSE_RULE,
        SOURCE_KIND_HTML,
        SOURCE_KIND_SLIDES,
    }
)


def infer_resource_kind(*values: object) -> str:
    """Infer a coarse resource kind from title-like metadata."""
    haystack = _casefold_join(values)
    if _contains_any(haystack, ("report", "レポート")):
        return RESOURCE_KIND_REPORT
    if _contains_any(haystack, ("課題", "assignment", "homework")):
        return RESOURCE_KIND_ASSIGNMENT
    if _contains_any(haystack, ("講義資料", "資料", "part", "slide", "slides")):
        return RESOURCE_KIND_MATERIAL
    if _contains_any(haystack, ("guide", "利用ガイド", "ガイド")):
        return RESOURCE_KIND_GUIDE
    return RESOURCE_KIND_UNKNOWN


def infer_task_resource_kind(*values: object) -> str:
    """Task list items are assignment-like unless metadata says report."""
    inferred = infer_resource_kind(*values)
    if inferred in {RESOURCE_KIND_REPORT, RESOURCE_KIND_ASSIGNMENT}:
        return inferred
    return RESOURCE_KIND_ASSIGNMENT


def normalize_resource_kind(value: object, *, fallback: str = RESOURCE_KIND_UNKNOWN) -> str:
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in RESOURCE_KINDS else fallback


def normalize_source_kind(value: object, *, fallback: str = SOURCE_KIND_FILESYSTEM) -> str:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "moocs-collect": SOURCE_KIND_MOOCS_COLLECT,
        "moocs_collect": SOURCE_KIND_MOOCS_COLLECT,
        "course-rule": SOURCE_KIND_COURSE_RULE,
        "course_rule": SOURCE_KIND_COURSE_RULE,
        "filesystem": SOURCE_KIND_FILESYSTEM,
        "file": SOURCE_KIND_FILESYSTEM,
        "html": SOURCE_KIND_HTML,
        "slides": SOURCE_KIND_SLIDES,
        "slide": SOURCE_KIND_SLIDES,
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in SOURCE_KINDS else fallback


def _casefold_join(values: Iterable[object]) -> str:
    return " ".join(str(value or "") for value in values).casefold()


def _contains_any(value: str, needles: Iterable[str]) -> bool:
    return any(needle.casefold() in value for needle in needles)
