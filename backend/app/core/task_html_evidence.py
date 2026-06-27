"""Attach lightweight HTML evidence from existing course detail JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.app.core.course_rules import normalize_course_code
from backend.app.core.task_list_composer import TaskEvidence


DEFAULT_HTML_EVIDENCE_LIMIT_PER_COURSE = 3
HTML_TASK_KEYWORDS = (
    "assignment",
    "exercise",
    "practice",
    "quiz",
    "review",
    "report",
)


def load_html_evidence_by_course(
    course_codes: list[str],
    path: Path,
    *,
    limit_per_course: int = DEFAULT_HTML_EVIDENCE_LIMIT_PER_COURSE,
) -> tuple[dict[str, list[TaskEvidence]], list[dict[str, str]]]:
    if not path.exists():
        return {}, []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [{"message": f"Could not load HTML evidence JSON: {exc}"}]

    selected_courses = {normalize_course_code(code) for code in course_codes}
    evidence_by_course: dict[str, list[TaskEvidence]] = {
        course_code: [] for course_code in selected_courses
    }

    for page in iter_pages(payload):
        page_url = str(page.get("page_url") or "").strip()
        if not page_url:
            continue

        course_code = course_code_from_page_url(page_url)
        if course_code not in selected_courses:
            continue
        if not looks_task_related(page):
            continue
        if len(evidence_by_course[course_code]) >= limit_per_course:
            continue

        evidence_by_course[course_code].append(
            TaskEvidence(
                type="html",
                label=html_evidence_label(page),
                source=page_url,
                confidence=html_evidence_confidence(page),
            )
        )

    return {
        course_code: evidence
        for course_code, evidence in evidence_by_course.items()
        if evidence
    }, []


def iter_pages(value: Any):
    if isinstance(value, dict):
        if isinstance(value.get("page_url"), str):
            yield value
        for child in value.values():
            yield from iter_pages(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_pages(item)


def course_code_from_page_url(page_url: str) -> str:
    parsed = urlparse(page_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    try:
        index = parts.index("courses")
    except ValueError:
        return ""
    if len(parts) <= index + 2:
        return ""
    return normalize_course_code(parts[index + 2])


def looks_task_related(page: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(page.get(key) or "")
        for key in ("page_title", "title", "page_url")
    ).lower()
    return any(keyword in haystack for keyword in HTML_TASK_KEYWORDS)


def html_evidence_label(page: dict[str, Any]) -> str:
    title = str(page.get("page_title") or page.get("title") or "").strip()
    if title:
        return title

    page_url = str(page.get("page_url") or "").strip()
    path = urlparse(page_url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or "HTML page"


def html_evidence_confidence(page: dict[str, Any]) -> str:
    page_url = str(page.get("page_url") or "").lower()
    if any(keyword in page_url for keyword in ("assignment", "report")):
        return "high"
    if any(keyword in page_url for keyword in HTML_TASK_KEYWORDS):
        return "medium"
    return "low"
