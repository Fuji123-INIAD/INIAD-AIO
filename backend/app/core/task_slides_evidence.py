"""Attach lightweight Slides evidence from probe JSON and MOOCs-Collect metadata."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from backend.app.core.course_rules import normalize_course_code
from backend.app.core.task_html_evidence import course_code_from_page_url, iter_pages
from backend.app.core.task_list_composer import TaskEvidence


DEFAULT_SLIDES_EVIDENCE_LIMIT_PER_COURSE = 3


def load_slides_evidence_by_course(
    course_codes: list[str],
    probe_json_path: Path,
    *,
    moocs_collect_db_path: Path | None = None,
    limit_per_course: int = DEFAULT_SLIDES_EVIDENCE_LIMIT_PER_COURSE,
) -> tuple[dict[str, list[TaskEvidence]], list[dict[str, str]]]:
    if not probe_json_path.exists():
        return {}, []

    try:
        payload = json.loads(probe_json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [{"message": f"Could not load Slides evidence JSON: {exc}"}]

    selected_courses = {normalize_course_code(code) for code in course_codes}
    evidence_by_course: dict[str, list[TaskEvidence]] = {
        course_code: [] for course_code in selected_courses
    }
    page_keys_by_course: dict[str, list[str]] = {
        course_code: [] for course_code in selected_courses
    }
    page_title_by_key: dict[str, str] = {}
    seen_page_keys: set[str] = set()

    for page in iter_pages(payload):
        page_url = str(page.get("page_url") or "").strip()
        if not page_url:
            continue

        course_code = course_code_from_page_url(page_url)
        if course_code not in selected_courses:
            continue

        page_key = page_url_to_key(page_url)
        if page_key and page_key not in seen_page_keys:
            seen_page_keys.add(page_key)
            page_keys_by_course[course_code].append(page_key)
            page_title_by_key[page_key] = slides_page_label(page)

        for evidence in slides_evidence_from_probe_page(page):
            if len(evidence_by_course[course_code]) >= limit_per_course:
                break
            evidence_by_course[course_code].append(evidence)

    warnings: list[dict[str, str]] = []
    if moocs_collect_db_path is not None and moocs_collect_db_path.exists():
        collect_evidence, collect_warnings = load_moocs_collect_slides_evidence(
            moocs_collect_db_path,
            page_keys_by_course,
            page_title_by_key,
        )
        warnings.extend(collect_warnings)
        for course_code, evidence_items in collect_evidence.items():
            remaining = limit_per_course - len(evidence_by_course[course_code])
            if remaining <= 0:
                continue
            evidence_by_course[course_code].extend(evidence_items[:remaining])
    elif moocs_collect_db_path is not None:
        warnings.append(
            {
                "message": (
                    f"MOOCs-Collect db.sqlite not found; Slides evidence skipped: "
                    f"{moocs_collect_db_path}"
                )
            }
        )

    return {
        course_code: evidence
        for course_code, evidence in evidence_by_course.items()
        if evidence
    }, warnings


def slides_evidence_from_probe_page(page: dict[str, Any]) -> list[TaskEvidence]:
    evidence_items: list[TaskEvidence] = []
    for material in page.get("materials") or []:
        if not isinstance(material, dict) or not looks_like_slides_material(material):
            continue
        source = str(
            material.get("material_url")
            or material.get("moocs_url")
            or material.get("url")
            or ""
        ).strip()
        if not source:
            continue
        evidence_items.append(
            TaskEvidence(
                type="slides",
                label=slides_material_label(page, material),
                source=source,
                confidence="high",
            )
        )
    return evidence_items


def load_moocs_collect_slides_evidence(
    db_path: Path,
    page_keys_by_course: dict[str, list[str]],
    page_title_by_key: dict[str, str],
) -> tuple[dict[str, list[TaskEvidence]], list[dict[str, str]]]:
    all_page_keys = [
        page_key
        for page_keys in page_keys_by_course.values()
        for page_key in page_keys
    ]
    if not all_page_keys:
        return {}, []

    try:
        with closing(open_readonly_database(db_path)) as connection:
            collect_rows = fetch_moocs_collect_slides(connection, all_page_keys)
    except Exception as exc:
        return {}, [{"message": f"Could not load MOOCs-Collect Slides evidence: {exc}"}]

    rows_by_key: dict[str, dict[str, Any]] = {
        str(row["page_key"]): row for row in collect_rows
    }
    evidence_by_course: dict[str, list[TaskEvidence]] = {
        course_code: [] for course_code in page_keys_by_course
    }

    for course_code, page_keys in page_keys_by_course.items():
        for page_key in page_keys:
            row = rows_by_key.get(page_key)
            if row is None or int(row["slide_count"]) <= 0:
                continue
            slide_url = str(row.get("first_slide_url") or "").strip()
            source = slide_url or page_key
            confidence = "high" if slide_url else "medium"
            evidence_by_course[course_code].append(
                TaskEvidence(
                    type="slides",
                    label=f"{page_title_by_key.get(page_key, page_key)} slides",
                    source=source,
                    confidence=confidence,
                )
            )

    return {
        course_code: evidence
        for course_code, evidence in evidence_by_course.items()
        if evidence
    }, []


def fetch_moocs_collect_slides(
    connection: sqlite3.Connection,
    page_keys: list[str],
) -> list[dict[str, Any]]:
    if not page_keys:
        return []

    slide_columns = table_columns(connection, "slides")
    url_expression = (
        "MIN(NULLIF(TRIM(s.\"url\"), ''))"
        if "url" in slide_columns
        else "NULL"
    )
    pdf_count_expression = (
        "SUM(CASE WHEN s.\"pdf_path\" IS NOT NULL AND TRIM(s.\"pdf_path\") != '' THEN 1 ELSE 0 END)"
        if "pdf_path" in slide_columns
        else "0"
    )
    placeholders = ", ".join("?" for _ in page_keys)
    rows = connection.execute(
        f"""
        SELECT
          p."key" AS page_key,
          COUNT(s."id") AS slide_count,
          {url_expression} AS first_slide_url,
          {pdf_count_expression} AS pdf_path_count
        FROM "pages" p
        JOIN "slides" s ON s."page_id" = p."id"
        WHERE p."key" IN ({placeholders})
        GROUP BY p."key"
        """,
        page_keys,
    ).fetchall()

    return [
        {
            "page_key": row[0],
            "slide_count": int(row[1] or 0),
            "first_slide_url": row[2],
            "pdf_path_count": int(row[3] or 0),
        }
        for row in rows
    ]


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def open_readonly_database(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"db.sqlite not found: {resolved}")
    return sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)


def page_url_to_key(page_url: str) -> str | None:
    parsed = urlparse(page_url.strip())
    path = parsed.path if parsed.scheme or parsed.netloc else page_url.strip()
    parts = [unquote(part) for part in path.split("/") if part]
    try:
        courses_index = parts.index("courses")
    except ValueError:
        return None

    key_parts = parts[courses_index + 1 :]
    if len(key_parts) != 4 or any(part.strip() == "" for part in key_parts):
        return None
    return "/".join(key_parts)


def looks_like_slides_material(material: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(material.get(key) or "")
        for key in (
            "material_type",
            "material_title",
            "retrieval_method",
            "material_url",
            "moocs_url",
            "url",
        )
    ).lower()
    return "slide" in haystack or "presentation" in haystack


def slides_material_label(page: dict[str, Any], material: dict[str, Any]) -> str:
    material_title = str(material.get("material_title") or "").strip()
    if material_title:
        return material_title
    return f"{slides_page_label(page)} slides"


def slides_page_label(page: dict[str, Any]) -> str:
    title = str(page.get("page_title") or page.get("title") or "").strip()
    if title:
        return title

    page_url = str(page.get("page_url") or "").strip()
    path = urlparse(page_url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or "MOOCs page"
