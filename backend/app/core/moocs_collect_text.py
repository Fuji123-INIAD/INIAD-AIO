"""Read MOOCs-Collect text into MaterialText records.

The real MOOCs-Collect db.sqlite stores metadata only.  Text usually lives in
the desktop Tantivy search_index, in Google Slides SVG aria-labels fetched at
download time, or in the PDFs generated from those SVGs.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from backend.app.core.material_text import (
    EXTRACTION_METHOD_APPDATA_HTML,
    EXTRACTION_METHOD_APPDATA_JSON,
    EXTRACTION_METHOD_APPDATA_SVG,
    EXTRACTION_METHOD_APPDATA_TEXT,
    EXTRACTION_METHOD_METADATA_ONLY,
    EXTRACTION_METHOD_MOOCS_COLLECT_SVG_TEXT,
    EXTRACTION_METHOD_OCR_MYPDF,
    EXTRACTION_METHOD_PYPDF,
    EXTRACTION_METHOD_PYMUPDF,
    EXTRACTION_METHOD_SEARCH_INDEX,
    SOURCE_TYPE_MOOCS_COLLECT_APPDATA_FILE,
    SOURCE_TYPE_MOOCS_COLLECT_PDF_NATIVE,
    SOURCE_TYPE_MOOCS_COLLECT_PDF_OCR,
    SOURCE_TYPE_MOOCS_COLLECT_SEARCH_INDEX,
    SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT,
    SOURCE_TYPE_PDF_METADATA,
    MaterialText,
    stable_material_id,
    utc_now_iso,
)
from backend.app.core.pdf_ocr_provider import (
    extract_pdf_native_text,
    extract_pdf_ocr_text,
)


MOOCS_COLLECT_PROVIDER = "moocs_collect"
PROVIDER_DB_METADATA = "moocs_collect_db_metadata"
PROVIDER_SEARCH_INDEX = "moocs_collect_search_index"
PROVIDER_APPDATA_FILE = "moocs_collect_appdata_file"
PROVIDER_PDF_NATIVE = "moocs_collect_pdf_path"
PROVIDER_PDF_OCR = "pdf_ocr_fallback"

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
APPDATA_TEXT_EXTENSIONS = {".json", ".html", ".htm", ".svg", ".txt", ".md", ".cache"}
SENSITIVE_PATH_PARTS = {
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "keyring",
    "password",
    "profile",
    "storage_state",
    "store.json",
    "token",
}
PAGE_KEY_PATTERN = re.compile(
    r"20\d{2}/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
)
GOOGLE_SLIDES_EMBED_PATTERN = re.compile(
    r"^https://docs\.google\.com/(?:a/[^/]+/)?presentation/d/(?:e/)?[^/]+/(?:embed|pubembed)\?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MoocsCollectSlideRecord:
    page_id: int | None
    page_key: str
    page_slug: str | None
    page_title: str | None
    slide_id: int | None
    slide_index: int | None
    slide_url: str | None
    pdf_path: str | None
    course_code: str | None = None
    course_title: str | None = None
    lecture_key: str | None = None
    lecture_title: str | None = None
    year: str | None = None

    def metadata(self) -> dict[str, Any]:
        parsed = metadata_from_page_key(self.page_key)
        return {
            "page_id": self.page_id,
            "page_key": self.page_key,
            "page_slug": self.page_slug or parsed.get("page_slug"),
            "page_title": self.page_title,
            "slide_id": self.slide_id,
            "slide_index": self.slide_index,
            "slide_url": self.slide_url,
            "pdf_path": self.pdf_path,
            "course_code": self.course_code or parsed.get("course_code"),
            "course_title": self.course_title,
            "lecture_key": self.lecture_key or parsed.get("lecture_key"),
            "lecture_title": self.lecture_title,
            "year": self.year or parsed.get("year"),
        }


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
    moocs_collect_root: Path | None = None,
    search_index: Path | None = None,
    include_search_index: bool = True,
    include_appdata_files: bool = False,
    include_slide_url_dom: bool = False,
    include_pdf_native: bool = True,
    include_pdf_ocr: bool = False,
    course_code: str | None = None,
    lecture_key: str | None = None,
    debug: bool = False,
) -> tuple[list[MaterialText], list[dict[str, str]]]:
    resolved_db_path = db_path.expanduser().resolve()
    root = (moocs_collect_root or resolved_db_path.parent).expanduser().resolve()
    resources = local_resources or []
    warnings: list[dict[str, str]] = []

    with closing(open_readonly_database(resolved_db_path)) as connection:
        schema = inspect_schema(connection)
        if not {"pages", "slides"}.issubset(schema):
            return [], [
                {
                    "message": (
                        "MOOCs-Collect DB does not have both pages and slides tables; "
                        "provider skipped."
                    )
                }
            ]
        records = load_metadata_records(
            connection,
            limit=limit,
            course_code=course_code,
            lecture_key=lecture_key,
        )
        legacy_text_columns = candidate_text_columns(schema.get("slides", []))
        legacy_materials = load_legacy_db_text_materials(
            connection,
            records,
            legacy_text_columns,
            resources,
        )

    materials: list[MaterialText] = []
    covered_page_keys: set[str] = set()
    covered_pdf_paths: set[str] = set()

    if include_search_index:
        resolved_search_index = resolve_search_index(root, search_index)
        if resolved_search_index and resolved_search_index.is_dir():
            search_materials, search_warnings = load_search_index_materials(
                resolved_search_index,
                records,
                resources,
                limit=limit,
            )
            materials.extend(search_materials)
            warnings.extend(search_warnings)
            covered_page_keys.update(material.source_ref or "" for material in search_materials)
        elif debug or search_index is not None:
            warnings.append(
                {
                    "message": (
                        "MOOCs-Collect search_index was not found or is not a directory; "
                        "search index provider skipped."
                    )
                }
            )

    if include_appdata_files and root.is_dir():
        appdata_materials, appdata_warnings = load_appdata_file_materials(
            root,
            records,
            resources,
            limit=limit,
        )
        appdata_materials = [
            material
            for material in appdata_materials
            if material.source_ref not in covered_page_keys
        ]
        materials.extend(appdata_materials)
        warnings.extend(appdata_warnings)
        covered_page_keys.update(material.source_ref or "" for material in appdata_materials)

    for material in legacy_materials:
        if material.source_ref in covered_page_keys:
            continue
        materials.append(material)
        if material.source_ref:
            covered_page_keys.add(material.source_ref)

    if include_slide_url_dom:
        warnings.append(
            {
                "message": (
                    "Slide URL DOM provider is optional and live-auth dependent; "
                    "use scripts/probe_moocs_collect_slide_urls.py for targeted probing."
                )
            }
        )

    if include_pdf_native:
        pdf_materials = load_pdf_native_materials(
            records,
            resources,
            covered_page_keys=covered_page_keys,
            limit=limit,
        )
        materials.extend(pdf_materials)
        covered_page_keys.update(material.source_ref or "" for material in pdf_materials)
        covered_pdf_paths.update(
            str(material.source_ref or "") for material in pdf_materials if material.source_ref
        )

    if include_pdf_ocr:
        ocr_materials = load_pdf_ocr_materials(
            records,
            resources,
            covered_page_keys=covered_page_keys,
            covered_pdf_paths=covered_pdf_paths,
            limit=limit,
        )
        materials.extend(ocr_materials)
        covered_page_keys.update(material.source_ref or "" for material in ocr_materials)

    metadata_materials = load_metadata_only_materials(
        records,
        resources,
        covered_page_keys=covered_page_keys,
    )
    materials.extend(metadata_materials)

    if not materials and debug:
        warnings.append({"message": "No MOOCs-Collect material records were produced."})

    return materials, warnings


def inspect_moocs_collect_text_quality(
    db_path: Path,
    *,
    local_resources: list[dict[str, Any]] | None = None,
    limit: int = 20,
    preview_chars: int = 160,
    moocs_collect_root: Path | None = None,
    search_index: Path | None = None,
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
        moocs_collect_root=moocs_collect_root,
        search_index=search_index,
    )
    text_blocks_found = sum(estimated_text_blocks(material) for material in materials)
    empty_slides = max(0, slide_count - min(slide_count, text_blocks_found)) if slide_count else 0
    samples = [
        {
            "course_code": material.course_code,
            "lecture_key": material.lecture_key,
            "lecture_title": material.lecture_title,
            "source_type": material.source_type,
            "provider": material.provider,
            "text_preview": material.text[:preview_chars],
        }
        for material in materials
        if material.text_available
    ][:5]
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
        "text_blocks_found": text_blocks_found,
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


def load_metadata_records(
    connection: sqlite3.Connection,
    *,
    limit: int | None,
    course_code: str | None,
    lecture_key: str | None,
) -> list[MoocsCollectSlideRecord]:
    schema = inspect_schema(connection)
    tables = set(schema)
    if {"courses", "lectures", "pages", "slides"}.issubset(tables):
        rows = fetch_full_metadata_rows(
            connection,
            limit=limit,
            course_code=course_code,
            lecture_key=lecture_key,
        )
    else:
        rows = fetch_minimal_metadata_rows(connection, limit=limit)
    return [record_from_row(row) for row in rows]


def fetch_full_metadata_rows(
    connection: sqlite3.Connection,
    *,
    limit: int | None,
    course_code: str | None,
    lecture_key: str | None,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if course_code:
        clauses.append("(c.slug = ? OR c.name LIKE ?)")
        params.extend([course_code, f"%{course_code}%"])
    if lecture_key:
        clauses.append("(l.slug = ? OR l.name LIKE ?)")
        params.extend([lecture_key, f"%{lecture_key}%"])
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    limit_sql = " LIMIT ?" if limit is not None else ""
    if limit is not None:
        params.append(max(0, limit))
    sql = f"""
        SELECT
          c.year AS year,
          c.slug AS course_code,
          c.name AS course_title,
          l.slug AS lecture_key,
          l.name AS lecture_title,
          p.id AS page_id,
          p.key AS page_key,
          p.slug AS page_slug,
          p.name AS page_title,
          s.id AS slide_id,
          s.idx AS slide_index,
          s.url AS slide_url,
          s.pdf_path AS pdf_path
        FROM slides s
        JOIN pages p ON p.id = s.page_id
        JOIN lectures l ON l.id = p.lecture_id
        JOIN courses c ON c.id = l.course_id
        {where_sql}
        ORDER BY c.year, c.sort_index, l.sort_index, p.sort_index, s.idx, s.id
        {limit_sql}
    """
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def fetch_minimal_metadata_rows(
    connection: sqlite3.Connection,
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    page_columns = schema_columns(connection, "pages")
    slide_columns = schema_columns(connection, "slides")
    page_key_expr = "p.\"key\"" if "key" in page_columns else "NULL"
    page_slug_expr = first_existing_sql("p", page_columns, ("slug",))
    page_title_expr = first_existing_sql("p", page_columns, ("title", "name", "page_title"))
    slide_index_expr = first_existing_sql("s", slide_columns, ("idx", "index", "slide_index", "number"))
    slide_url_expr = first_existing_sql("s", slide_columns, ("url", "slide_url"))
    pdf_path_expr = first_existing_sql("s", slide_columns, ("pdf_path", "path", "file_path"))
    limit_sql = " LIMIT ?" if limit is not None else ""
    params: tuple[Any, ...] = (max(0, limit),) if limit is not None else ()
    sql = f"""
        SELECT
          p."id" AS page_id,
          {page_key_expr} AS page_key,
          {page_slug_expr} AS page_slug,
          {page_title_expr} AS page_title,
          s."id" AS slide_id,
          {slide_index_expr} AS slide_index,
          {slide_url_expr} AS slide_url,
          {pdf_path_expr} AS pdf_path
        FROM "pages" p
        JOIN "slides" s ON s."page_id" = p."id"
        ORDER BY p."id", s."id"
        {limit_sql}
    """
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def record_from_row(row: dict[str, Any]) -> MoocsCollectSlideRecord:
    page_key = str(row.get("page_key") or f"page:{row.get('page_id') or 'unknown'}")
    parsed = metadata_from_page_key(page_key)
    return MoocsCollectSlideRecord(
        page_id=int_or_none(row.get("page_id")),
        page_key=page_key,
        page_slug=nullable_text(row.get("page_slug")) or parsed.get("page_slug"),
        page_title=nullable_text(row.get("page_title")),
        slide_id=int_or_none(row.get("slide_id")),
        slide_index=int_or_none(row.get("slide_index")),
        slide_url=nullable_text(row.get("slide_url")),
        pdf_path=nullable_text(row.get("pdf_path")),
        course_code=nullable_text(row.get("course_code")) or parsed.get("course_code"),
        course_title=nullable_text(row.get("course_title")),
        lecture_key=nullable_text(row.get("lecture_key")) or parsed.get("lecture_key"),
        lecture_title=nullable_text(row.get("lecture_title")),
        year=nullable_text(row.get("year")) or parsed.get("year"),
    )


def load_legacy_db_text_materials(
    connection: sqlite3.Connection,
    records: list[MoocsCollectSlideRecord],
    text_columns: list[str],
    local_resources: list[dict[str, Any]],
) -> list[MaterialText]:
    if not text_columns:
        return []
    grouped: dict[str, list[tuple[MoocsCollectSlideRecord, str]]] = defaultdict(list)
    selected_text = ", ".join(quote_identifier(column) for column in text_columns)
    for record in records:
        if record.slide_id is None:
            continue
        row = connection.execute(
            f"SELECT {selected_text} FROM slides WHERE id = ?",
            (record.slide_id,),
        ).fetchone()
        if row is None:
            continue
        text_parts = []
        for column in text_columns:
            value = row[column]
            if value is None:
                continue
            decoded = decode_text_blob(str(value))
            text_parts.append(extract_aria_labels_from_markup(decoded) or decoded)
        text = compact_text("\n".join(text_parts))
        if text:
            grouped[record.page_key].append((record, text))

    materials = []
    for page_key, rows in grouped.items():
        first_record = rows[0][0]
        slide_blocks = []
        for record, text in sorted(rows, key=lambda item: item[0].slide_index or 0):
            slide_blocks.append(f"Slide {record.slide_index}: {text}")
        materials.append(
            material_from_record(
                first_record,
                "\n\n".join(slide_blocks),
                local_resources,
                source_type=SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT,
                extraction_method=EXTRACTION_METHOD_MOOCS_COLLECT_SVG_TEXT,
                provider=MOOCS_COLLECT_PROVIDER,
                source_ref=page_key,
                text_available=True,
            )
        )
    return materials


def load_search_index_materials(
    search_index: Path,
    records: list[MoocsCollectSlideRecord],
    local_resources: list[dict[str, Any]],
    *,
    limit: int | None,
) -> tuple[list[MaterialText], list[dict[str, str]]]:
    warnings = []
    engine = infer_search_index_engine(search_index)
    if engine != "tantivy":
        warnings.append({"message": f"Unsupported search_index engine: {engine}"})
        return [], warnings

    extracted = extract_tantivy_store_texts(search_index, limit=limit)
    if not extracted:
        warnings.append(
            {
                "message": (
                    "Tantivy search_index exists, but no stored text could be extracted. "
                    "Install a Tantivy reader or use PDF/DOM fallback."
                )
            }
        )
        return [], warnings

    record_by_page_key = first_record_by_page_key(records)
    materials = []
    for page_key, text in extracted.items():
        if record_by_page_key and page_key not in record_by_page_key:
            continue
        record = record_by_page_key.get(page_key) or record_from_page_key(page_key)
        materials.append(
            material_from_record(
                record,
                text,
                local_resources,
                source_type=SOURCE_TYPE_MOOCS_COLLECT_SEARCH_INDEX,
                extraction_method=EXTRACTION_METHOD_SEARCH_INDEX,
                provider=PROVIDER_SEARCH_INDEX,
                source_ref=page_key,
                text_available=True,
            )
        )
    return materials, warnings


def extract_tantivy_store_texts(search_index: Path, *, limit: int | None = None) -> dict[str, str]:
    page_texts: dict[str, list[str]] = defaultdict(list)
    for store_file in sorted(search_index.glob("*.store")):
        try:
            decoded = store_file.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            continue
        matches = list(PAGE_KEY_PATTERN.finditer(decoded))
        for index, match in enumerate(matches):
            page_key = match.group(0)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(decoded)
            segment = decoded[match.start() : end]
            text = clean_tantivy_store_segment(segment, page_key)
            if looks_cross_page_contaminated(text, page_key):
                continue
            if len(text) >= 20:
                page_texts[page_key].append(text)
        if limit is not None and len(page_texts) >= limit:
            break

    best: dict[str, str] = {}
    for page_key, candidates in page_texts.items():
        unique = dedupe_texts(candidates)
        best[page_key] = max(unique, key=len)
    if limit is not None:
        return dict(list(best.items())[: max(0, limit)])
    return best


def clean_tantivy_store_segment(segment: str, page_key: str) -> str:
    text = segment
    meta_pos = text.find('{"version"')
    if meta_pos >= 0:
        text = text[:meta_pos]
    text = text.replace(page_key, " ")
    text = "".join(char if is_readable_text_char(char) else " " for char in text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = []
    seen = set()
    for line in text.splitlines():
        cleaned = compact_text(line)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        lines.append(cleaned)
    return "\n".join(lines).strip()


def is_readable_text_char(char: str) -> bool:
    if char in "\n\t ":
        return True
    category = unicodedata.category(char)
    if category.startswith("C"):
        return False
    return char != "\ufffd"


def looks_cross_page_contaminated(text: str, page_key: str) -> bool:
    metadata = metadata_from_page_key(page_key)
    current_course = str(metadata.get("course_code") or "")
    head = text[:500]
    course_markers = re.findall(r"(?:20\d{2}/|/)([A-Z]{2,4}\d{3})/", head)
    return any(marker != current_course for marker in course_markers)


def load_appdata_file_materials(
    root: Path,
    records: list[MoocsCollectSlideRecord],
    local_resources: list[dict[str, Any]],
    *,
    limit: int | None,
) -> tuple[list[MaterialText], list[dict[str, str]]]:
    page_texts: dict[str, tuple[str, str, str]] = {}
    warnings = []
    record_by_page_key = first_record_by_page_key(records)
    files_checked = 0
    for path in iter_appdata_text_files(root):
        files_checked += 1
        if limit is not None and files_checked > max(0, limit) * 20:
            break
        text, method = extract_text_from_appdata_file(path)
        if not text:
            continue
        page_key = find_page_key_for_appdata_text(path, text, records)
        if not page_key:
            continue
        previous = page_texts.get(page_key)
        if previous is None or len(text) > len(previous[0]):
            page_texts[page_key] = (text, method, str(path))

    materials = []
    for page_key, (text, method, source_path) in page_texts.items():
        record = record_by_page_key.get(page_key) or record_from_page_key(page_key)
        materials.append(
            material_from_record(
                record,
                text,
                local_resources,
                source_type=SOURCE_TYPE_MOOCS_COLLECT_APPDATA_FILE,
                extraction_method=method,
                provider=PROVIDER_APPDATA_FILE,
                source_ref=page_key,
                text_available=True,
                extra_warnings=[{"message": f"AppData text source: {Path(source_path).name}"}],
            )
        )
    if not materials and files_checked == 0:
        warnings.append({"message": "No safe AppData text files were found."})
    return materials, warnings


def load_pdf_native_materials(
    records: list[MoocsCollectSlideRecord],
    local_resources: list[dict[str, Any]],
    *,
    covered_page_keys: set[str],
    limit: int | None,
) -> list[MaterialText]:
    materials = []
    checked = 0
    for record in records:
        if record.page_key in covered_page_keys:
            continue
        if not record.pdf_path:
            continue
        pdf_path = Path(record.pdf_path).expanduser()
        if not pdf_path.is_file():
            continue
        checked += 1
        if limit is not None and checked > max(0, limit):
            break
        result = extract_pdf_native_text(pdf_path)
        if not result.text_available:
            continue
        method = (
            EXTRACTION_METHOD_PYMUPDF
            if result.extraction_method == "pymupdf"
            else EXTRACTION_METHOD_PYPDF
        )
        materials.append(
            material_from_record(
                record,
                result.text,
                local_resources,
                source_type=SOURCE_TYPE_MOOCS_COLLECT_PDF_NATIVE,
                extraction_method=method,
                provider=PROVIDER_PDF_NATIVE,
                source_ref=record.page_key,
                text_available=True,
                extra_warnings=result.warnings,
            )
        )
    return materials


def load_pdf_ocr_materials(
    records: list[MoocsCollectSlideRecord],
    local_resources: list[dict[str, Any]],
    *,
    covered_page_keys: set[str],
    covered_pdf_paths: set[str],
    limit: int | None,
) -> list[MaterialText]:
    materials = []
    checked = 0
    for record in records:
        if record.page_key in covered_page_keys:
            continue
        if not record.pdf_path or record.pdf_path in covered_pdf_paths:
            continue
        pdf_path = Path(record.pdf_path).expanduser()
        if not pdf_path.is_file():
            continue
        checked += 1
        if limit is not None and checked > max(0, limit):
            break
        result = extract_pdf_ocr_text(pdf_path)
        if not result.text_available:
            continue
        materials.append(
            material_from_record(
                record,
                result.text,
                local_resources,
                source_type=SOURCE_TYPE_MOOCS_COLLECT_PDF_OCR,
                extraction_method=EXTRACTION_METHOD_OCR_MYPDF,
                provider=PROVIDER_PDF_OCR,
                source_ref=record.page_key,
                text_available=True,
                extra_warnings=result.warnings,
            )
        )
    return materials


def load_metadata_only_materials(
    records: list[MoocsCollectSlideRecord],
    local_resources: list[dict[str, Any]],
    *,
    covered_page_keys: set[str],
) -> list[MaterialText]:
    materials = []
    seen = set()
    for record in records:
        if record.page_key in covered_page_keys or record.page_key in seen:
            continue
        seen.add(record.page_key)
        metadata = record.metadata()
        text = metadata_text(metadata)
        materials.append(
            material_from_record(
                record,
                text,
                local_resources,
                source_type=SOURCE_TYPE_PDF_METADATA,
                extraction_method=EXTRACTION_METHOD_METADATA_ONLY,
                provider=PROVIDER_DB_METADATA,
                source_ref=record.page_key,
                text_available=False,
                extra_warnings=[
                    {
                        "message": (
                            "MOOCs-Collect DB has metadata only for this page; "
                            "body text was not extracted."
                        )
                    }
                ],
            )
        )
    return materials


def material_from_record(
    record: MoocsCollectSlideRecord,
    text: str,
    local_resources: list[dict[str, Any]],
    *,
    source_type: str,
    extraction_method: str,
    provider: str,
    source_ref: str,
    text_available: bool,
    extra_warnings: list[dict[str, str]] | None = None,
) -> MaterialText:
    metadata = record.metadata()
    joined_resource, confidence = find_join_resource(metadata, local_resources)
    warnings = list(extra_warnings or [])
    if confidence in {"low", "none"}:
        warnings.append(
            {
                "message": (
                    f"LocalResource join confidence is {confidence}; "
                    "source mapping should be checked before presentation."
                )
            }
        )
    title = first_text(
        metadata.get("page_title"),
        Path(str(metadata.get("pdf_path") or "")).name,
        joined_resource.get("title") if joined_resource else None,
        source_ref,
    )
    material_id = stable_material_id(
        "moocs-collect",
        source_type,
        source_ref,
        metadata.get("pdf_path"),
        title,
    )
    source_url = first_text(metadata.get("slide_url"))
    if not source_url and joined_resource and joined_resource.get("resource_id"):
        source_url = f"/api/local/resources/{joined_resource['resource_id']}/file"
    body = compact_preserve_lines(text)
    return MaterialText(
        material_id=material_id,
        course_code=nullable_text(
            first_text(metadata.get("course_code"), joined_resource.get("course_code") if joined_resource else None)
        ),
        course_title=nullable_text(
            first_text(metadata.get("course_title"), joined_resource.get("course_title") if joined_resource else None)
        ),
        lecture_key=nullable_text(
            first_text(metadata.get("lecture_key"), joined_resource.get("lecture_key") if joined_resource else None)
        ),
        lecture_title=nullable_text(
            first_text(metadata.get("lecture_title"), joined_resource.get("lecture_title") if joined_resource else None)
        ),
        title=title or "Untitled MOOCs-Collect material",
        source_type=source_type,
        source_ref=source_ref,
        source_url=source_url or None,
        local_resource_id=joined_resource.get("resource_id") if joined_resource else None,
        text_available=bool(text_available and body),
        extraction_method=extraction_method,
        provider=provider,
        text=body,
        text_length=len(body),
        language="ja",
        warnings=warnings,
        indexed_at=utc_now_iso(),
    )


def inspect_schema(connection: sqlite3.Connection) -> dict[str, list[str]]:
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {table: schema_columns(connection, table) for table in tables}


def schema_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
    ]


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return schema_columns(connection, table)


def table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(
        connection.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
    )


def candidate_text_columns(columns: list[str]) -> list[str]:
    return [
        column
        for column in columns
        if any(hint in column.lower() for hint in TEXT_COLUMN_HINTS)
    ]


def fetch_slide_rows(
    connection: sqlite3.Connection,
    text_columns: list[str],
    page_columns: list[str],
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    del text_columns, page_columns
    return [record.metadata() for record in load_metadata_records(
        connection,
        limit=limit,
        course_code=None,
        lecture_key=None,
    )]


def first_existing_sql(alias: str, columns: list[str], names: tuple[str, ...]) -> str:
    for name in names:
        if name in columns:
            return f"{alias}.{quote_identifier(name)}"
    return "NULL"


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


def extract_svg_text(value: str) -> str:
    aria_text = extract_aria_labels_from_markup(value)
    if aria_text:
        return aria_text
    text_nodes = re.findall(r"<text\b[^>]*>(.*?)</text>", value, flags=re.IGNORECASE | re.DOTALL)
    return compact_text(" ".join(strip_tags(node) for node in text_nodes))


def extract_html_text(value: str) -> str:
    without_scripts = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", value, flags=re.I | re.S)
    aria_text = extract_aria_labels_from_markup(without_scripts)
    visible = strip_tags(without_scripts)
    return compact_text("\n".join(part for part in (aria_text, visible) if part))


def extract_json_text(value: Any) -> str:
    texts = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if isinstance(item, (str, int, float)) and (
                any(hint in lowered for hint in TEXT_COLUMN_HINTS)
                or lowered in {"title", "name", "label"}
            ):
                texts.append(str(item))
            elif isinstance(item, (dict, list)):
                texts.append(extract_json_text(item))
    elif isinstance(value, list):
        for item in value:
            texts.append(extract_json_text(item))
    return compact_text(" ".join(text for text in texts if text))


def extract_text_from_appdata_file(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "", EXTRACTION_METHOD_APPDATA_TEXT
    suffix = path.suffix.lower()
    if suffix == ".svg":
        return extract_svg_text(raw), EXTRACTION_METHOD_APPDATA_SVG
    if suffix in {".html", ".htm"}:
        return extract_html_text(raw), EXTRACTION_METHOD_APPDATA_HTML
    if suffix == ".json":
        try:
            return extract_json_text(json.loads(raw)), EXTRACTION_METHOD_APPDATA_JSON
        except Exception:
            return compact_text(raw[:5000]), EXTRACTION_METHOD_APPDATA_JSON
    return compact_text(raw), EXTRACTION_METHOD_APPDATA_TEXT


def iter_appdata_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in APPDATA_TEXT_EXTENSIONS:
            continue
        if has_sensitive_path(path):
            continue
        if "search_index" in {part.lower() for part in path.parts}:
            continue
        yield path


def find_page_key_for_appdata_text(
    path: Path,
    text: str,
    records: list[MoocsCollectSlideRecord],
) -> str | None:
    match = PAGE_KEY_PATTERN.search(text)
    if match:
        return match.group(0)
    path_text = "/".join(path.parts).casefold()
    for record in records:
        if record.page_key and record.page_key.casefold() in path_text:
            return record.page_key
        if record.page_slug and record.page_slug.casefold() in path_text:
            return record.page_key
    return None


def metadata_from_page_key(page_key: str) -> dict[str, str | None]:
    parts = [part for part in str(page_key or "").split("/") if part]
    return {
        "year": parts[0] if len(parts) > 0 else None,
        "course_code": parts[1] if len(parts) > 1 else None,
        "lecture_key": parts[2] if len(parts) > 2 else None,
        "page_slug": parts[3] if len(parts) > 3 else None,
    }


def record_from_page_key(page_key: str) -> MoocsCollectSlideRecord:
    parsed = metadata_from_page_key(page_key)
    return MoocsCollectSlideRecord(
        page_id=None,
        page_key=page_key,
        page_slug=parsed.get("page_slug"),
        page_title=parsed.get("page_slug"),
        slide_id=None,
        slide_index=None,
        slide_url=None,
        pdf_path=None,
        course_code=parsed.get("course_code"),
        lecture_key=parsed.get("lecture_key"),
        year=parsed.get("year"),
    )


def find_join_resource(
    metadata: dict[str, Any],
    resources: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    page_key = str(metadata.get("page_key") or "")
    pdf_path = str(metadata.get("pdf_path") or "")
    course_code = str(metadata.get("course_code") or "")
    lecture_key = str(metadata.get("lecture_key") or "")
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


def parse_slide_url_kind(url: str | None) -> dict[str, Any]:
    value = str(url or "").strip()
    parsed = urlparse(value)
    path = parsed.path or ""
    host = parsed.netloc.lower()
    return {
        "url": value,
        "host": host,
        "path": path,
        "is_google_slides": bool(GOOGLE_SLIDES_EMBED_PATTERN.search(value)),
        "is_moocs": "moocs" in host or "iniad" in host,
        "is_pdf": path.lower().endswith(".pdf"),
        "is_file_url": parsed.scheme == "file",
        "path_pattern": summarize_url_path(path),
    }


def summarize_url_path(path: str) -> str:
    parts = [part for part in str(path or "").split("/") if part]
    if len(parts) >= 5 and parts[:3] == ["presentation", "d", "e"]:
        return f"/presentation/d/e/<deck>/{parts[4]}"
    if len(parts) >= 4 and parts[:2] == ["presentation", "d"]:
        return f"/presentation/d/<deck>/{parts[3]}"
    if not parts:
        return "/"
    return "/" + "/".join(parts[:4]) + ("/..." if len(parts) > 4 else "")


def resolve_search_index(root: Path, search_index: Path | None) -> Path | None:
    if search_index is not None:
        return search_index.expanduser().resolve()
    candidate = root / "search_index"
    return candidate if candidate.exists() else None


def infer_search_index_engine(search_index: Path) -> str:
    if not search_index.exists():
        return "missing"
    names = {path.name for path in search_index.iterdir()}
    suffix_counts = Counter(path.suffix.lower() for path in search_index.iterdir() if path.is_file())
    if "meta.json" in names and any(
        suffix in suffix_counts
        for suffix in (".store", ".term", ".idx", ".pos", ".fast", ".fieldnorm")
    ):
        return "tantivy"
    if any(path.suffix in {".sqlite", ".db"} for path in search_index.iterdir() if path.is_file()):
        return "sqlite_fts"
    if any(path.suffix == ".json" for path in search_index.iterdir() if path.is_file()):
        return "json_search_index"
    return "unknown"


def first_record_by_page_key(
    records: list[MoocsCollectSlideRecord],
) -> dict[str, MoocsCollectSlideRecord]:
    result = {}
    for record in records:
        result.setdefault(record.page_key, record)
    return result


def estimated_text_blocks(material: MaterialText) -> int:
    if not material.text_available:
        return 0
    slide_markers = len(re.findall(r"^Slide\s+\d+", material.text, flags=re.MULTILINE))
    page_markers = len(re.findall(r"^Page\s+\d+", material.text, flags=re.MULTILINE))
    return max(1, slide_markers, page_markers)


def metadata_text(metadata: dict[str, Any]) -> str:
    return " / ".join(
        str(value).strip()
        for value in (
            metadata.get("course_code"),
            metadata.get("course_title"),
            metadata.get("lecture_key"),
            metadata.get("lecture_title"),
            metadata.get("page_title"),
            Path(str(metadata.get("pdf_path") or "")).name,
        )
        if str(value or "").strip()
    )


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value))


def compact_text(value: str) -> str:
    return " ".join(str(value or "").split())


def compact_preserve_lines(value: str) -> str:
    lines = [" ".join(line.split()) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def dedupe_texts(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = compact_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def has_sensitive_path(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    return any(sensitive in part for part in lowered for sensitive in SENSITIVE_PATH_PARTS)


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def int_or_none(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
