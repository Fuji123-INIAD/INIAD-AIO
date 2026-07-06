"""Read MOOCs-Collect slide text into MaterialText records."""

from __future__ import annotations

import html
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from backend.app.core.material_text import (
    EXTRACTION_METHOD_MOOCS_COLLECT_SVG_TEXT,
    SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT,
    MaterialText,
    stable_material_id,
    utc_now_iso,
)


MOOCS_COLLECT_PROVIDER = "moocs_collect"
TEXT_COLUMN_HINTS = (
    "text",
    "content",
    "body",
    "markdown",
    "transcript",
    "extracted",
    "svg",
    "aria",
    "label",
    "html",
)


def open_readonly_database(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"db.sqlite not found: {resolved}")
    connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def load_moocs_collect_material_texts(
    db_path: Path,
    *,
    local_resources: list[dict[str, Any]] | None = None,
    limit: int | None = None,
) -> tuple[list[MaterialText], list[dict[str, str]]]:
    resolved_db_path = db_path.expanduser().resolve()
    warnings: list[dict[str, str]] = []
    with closing(open_readonly_database(resolved_db_path)) as connection:
        schema = inspect_schema(connection)
        if not {"pages", "slides"}.issubset(schema):
            return [], [
                {
                    "message": (
                        "MOOCs-Collect DB does not have both pages and slides tables; "
                        "slide text provider skipped."
                    )
                }
            ]
        slide_columns = schema["slides"]
        page_columns = schema["pages"]
        text_columns = candidate_text_columns(slide_columns)
        if not text_columns:
            return [], [
                {
                    "message": (
                        "MOOCs-Collect slides table has no obvious text columns. "
                        "Use the probe script to inspect whether text is stored in another table."
                    )
                }
            ]
        rows = fetch_slide_rows(connection, text_columns, page_columns, limit=limit)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        text = extract_text_from_row(row, text_columns)
        if not text:
            continue
        key = str(row.get("page_key") or f"page:{row.get('page_id')}")
        grouped[key].append({**row, "text": text})

    resources = local_resources or []
    materials: list[MaterialText] = []
    for page_key, slide_rows in grouped.items():
        first = slide_rows[0]
        metadata = metadata_from_page_key(page_key)
        joined_resource, confidence = find_join_resource(first, metadata, resources)
        warnings_for_material = []
        if confidence in {"low", "none"}:
            warnings_for_material.append(
                {
                    "message": (
                        f"LocalResource join confidence is {confidence}; "
                        "source mapping should be checked before presentation."
                    )
                }
            )
        slide_blocks = []
        for slide in sorted(slide_rows, key=lambda item: int(item.get("slide_index") or 0)):
            slide_index = slide.get("slide_index")
            slide_blocks.append(f"Slide {slide_index}: {slide['text']}")
        text = "\n\n".join(slide_blocks)
        title = first_text(
            first.get("page_title"),
            first.get("pdf_path"),
            joined_resource.get("title") if joined_resource else None,
            page_key,
        )
        material_id = stable_material_id(
            "moocs-collect",
            page_key,
            first.get("pdf_path"),
            title,
        )
        source_url = first_text(first.get("slide_url"), first.get("page_url"))
        if not source_url and joined_resource:
            source_url = None
        materials.append(
            MaterialText(
                material_id=material_id,
                course_code=first_text(metadata.get("course_code"), joined_resource.get("course_code") if joined_resource else None) or None,
                course_title=joined_resource.get("course_title") if joined_resource else None,
                lecture_key=first_text(metadata.get("lecture_key"), joined_resource.get("lecture_key") if joined_resource else None) or None,
                lecture_title=joined_resource.get("lecture_title") if joined_resource else None,
                title=title,
                source_type=SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT,
                source_ref=page_key,
                source_url=source_url or (
                    f"/api/local/resources/{joined_resource['resource_id']}/file"
                    if joined_resource and joined_resource.get("resource_id")
                    else None
                ),
                local_resource_id=joined_resource.get("resource_id") if joined_resource else None,
                text_available=True,
                extraction_method=EXTRACTION_METHOD_MOOCS_COLLECT_SVG_TEXT,
                provider=MOOCS_COLLECT_PROVIDER,
                text=text,
                text_length=len(text),
                language="ja",
                warnings=warnings_for_material,
                indexed_at=utc_now_iso(),
            )
        )

    return materials, warnings


def inspect_moocs_collect_text_quality(
    db_path: Path,
    *,
    local_resources: list[dict[str, Any]] | None = None,
    limit: int = 20,
    preview_chars: int = 160,
) -> dict[str, Any]:
    resolved_db_path = db_path.expanduser().resolve()
    with closing(open_readonly_database(resolved_db_path)) as connection:
        schema = inspect_schema(connection)
        page_count = table_count(connection, "pages") if "pages" in schema else 0
        slide_count = table_count(connection, "slides") if "slides" in schema else 0
        text_columns = candidate_text_columns(schema.get("slides", []))
    materials, warnings = load_moocs_collect_material_texts(
        resolved_db_path,
        local_resources=local_resources,
        limit=limit,
    )
    chunks_found = sum(material.text.count("Slide ") for material in materials)
    empty_slides = max(0, slide_count - chunks_found) if slide_count else 0
    samples = [
        {
            "course_code": material.course_code,
            "lecture_key": material.lecture_key,
            "lecture_title": material.lecture_title,
            "slide_index": first_slide_index(material.text),
            "text_preview": material.text[:preview_chars],
        }
        for material in materials[:5]
    ]
    join_candidates = [
        {
            "resource_id": material.local_resource_id,
            "resource_title": material.title,
            "matched_page_key": material.source_ref,
            "join_confidence": "medium" if material.local_resource_id else "none",
        }
        for material in materials[:10]
    ]
    return {
        "status": "ok",
        "db_path": str(resolved_db_path),
        "courses_checked": len({material.course_code for material in materials if material.course_code}),
        "pages_checked": page_count,
        "slides_checked": slide_count,
        "text_blocks_found": chunks_found,
        "empty_slides": empty_slides,
        "text_columns": text_columns,
        "sample_items": samples,
        "join_candidates": join_candidates,
        "warnings": warnings,
        "safety": {
            "db_read_only": True,
            "full_text_saved": False,
            "raw_html_saved": False,
            "sensitive_files_read": False,
        },
    }


def inspect_schema(connection: sqlite3.Connection) -> dict[str, list[str]]:
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {table: table_columns(connection, table) for table in tables}


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
    ]


def table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(
        connection.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
    )


def candidate_text_columns(columns: list[str]) -> list[str]:
    candidates = []
    for column in columns:
        lowered = column.lower()
        if any(hint in lowered for hint in TEXT_COLUMN_HINTS):
            candidates.append(column)
    return candidates


def fetch_slide_rows(
    connection: sqlite3.Connection,
    text_columns: list[str],
    page_columns: list[str],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    page_key_expr = "p.\"key\"" if "key" in page_columns else "NULL"
    page_title_expr = first_existing_sql("p", page_columns, ("title", "name", "page_title"))
    page_url_expr = first_existing_sql("p", page_columns, ("url", "page_url"))
    slide_columns = table_columns(connection, "slides")
    slide_index_expr = first_existing_sql("s", slide_columns, ("idx", "index", "slide_index", "number"))
    slide_url_expr = first_existing_sql("s", slide_columns, ("url", "slide_url"))
    pdf_path_expr = first_existing_sql("s", slide_columns, ("pdf_path", "path", "file_path"))
    selected_text = ", ".join(
        f"s.{quote_identifier(column)} AS {quote_identifier('text__' + column)}"
        for column in text_columns
    )
    limit_sql = " LIMIT ?" if limit is not None else ""
    params: tuple[Any, ...] = (max(0, limit),) if limit is not None else ()
    sql = f"""
        SELECT
          p."id" AS page_id,
          {page_key_expr} AS page_key,
          {page_title_expr} AS page_title,
          {page_url_expr} AS page_url,
          s."id" AS slide_id,
          {slide_index_expr} AS slide_index,
          {slide_url_expr} AS slide_url,
          {pdf_path_expr} AS pdf_path,
          {selected_text}
        FROM "pages" p
        JOIN "slides" s ON s."page_id" = p."id"
        ORDER BY p."id", s."id"
        {limit_sql}
    """
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def first_existing_sql(alias: str, columns: list[str], names: tuple[str, ...]) -> str:
    for name in names:
        if name in columns:
            return f"{alias}.{quote_identifier(name)}"
    return "NULL"


def extract_text_from_row(row: dict[str, Any], text_columns: list[str]) -> str:
    texts = []
    for column in text_columns:
        value = row.get("text__" + column)
        if value is None:
            continue
        text = decode_text_blob(str(value))
        extracted = extract_aria_labels_from_markup(text)
        texts.append(extracted or text)
    joined = "\n".join(part.strip() for part in texts if part and part.strip())
    return compact_text(joined)


def decode_text_blob(value: str) -> str:
    decoded = value
    for _ in range(3):
        next_value = html.unescape(unquote(decoded))
        next_value = (
            next_value.replace("\\u003c", "<")
            .replace("\\u003C", "<")
            .replace("\\x3c", "<")
            .replace("\\x3C", "<")
            .replace("\\u003e", ">")
            .replace("\\u003E", ">")
            .replace("\\x3e", ">")
            .replace("\\x3E", ">")
            .replace('\\"', '"')
            .replace("\\/", "/")
        )
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def extract_aria_labels_from_markup(value: str) -> str:
    labels = re.findall(r'aria-label=["\']([^"\']+)["\']', value, flags=re.IGNORECASE)
    return "\n".join(compact_text(html.unescape(label)) for label in labels if label.strip())


def compact_text(value: str) -> str:
    return " ".join(str(value or "").split())


def metadata_from_page_key(page_key: str) -> dict[str, str | None]:
    parts = [part for part in str(page_key or "").split("/") if part]
    return {
        "year": parts[0] if len(parts) > 0 else None,
        "course_code": parts[1] if len(parts) > 1 else None,
        "lecture_key": parts[2] if len(parts) > 2 else None,
        "page_slug": parts[3] if len(parts) > 3 else None,
    }


def find_join_resource(
    row: dict[str, Any],
    metadata: dict[str, str | None],
    resources: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    page_key = str(row.get("page_key") or "")
    pdf_path = str(row.get("pdf_path") or "")
    course_code = metadata.get("course_code")
    lecture_key = metadata.get("lecture_key")
    for resource in resources:
        if page_key and str(resource.get("page_key") or "") == page_key:
            return resource, "high"
    for resource in resources:
        title = str(resource.get("title") or "")
        local_path = str(resource.get("local_path") or "")
        if pdf_path and (Path(pdf_path).name == title or pdf_path in local_path):
            return resource, "high"
    for resource in resources:
        if course_code and str(resource.get("course_code") or "") == course_code:
            if lecture_key and str(resource.get("lecture_key") or "") == lecture_key:
                return resource, "medium"
    for resource in resources:
        if course_code and str(resource.get("course_code") or "") == course_code:
            return resource, "low"
    return None, "none"


def first_slide_index(text: str) -> int | None:
    match = re.search(r"Slide\s+(\d+)", text)
    return int(match.group(1)) if match else None


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
