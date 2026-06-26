"""Probe short keyword contexts from MOOCs-Collect PDF text layers."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

from scripts.check_moocs_collect_page_join import (
    load_aio_page_keys,
    open_readonly_database,
    quote_identifier,
    resolve_pdf_path,
)


KEYWORDS = (
    "課題",
    "提出",
    "締切",
    "期限",
    "レポート",
    "小テスト",
    "quiz",
    "report",
    "assignment",
    "due",
    "deadline",
    "提出期限",
    "回答",
    "フォーム",
)

DEADLINE_PATTERNS = (
    re.compile(r"\d{1,2}月\d{1,2}日(?:[月火水木金土日]曜日?)?\s*\d{1,2}時\d{1,2}分"),
    re.compile(r"\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}"),
    re.compile(r"20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}"),
    re.compile(r"次の講義前日まで"),
    re.compile(r"次回講義まで"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read only PDF text layers for MOOCs-Collect slides matched from AIO "
            "page_url keys, and print bounded keyword/deadline snippets only."
        )
    )
    parser.add_argument("probe_json", type=Path, help="Path to AIO probe JSON")
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite")
    parser.add_argument(
        "--download-dir",
        type=Path,
        required=True,
        help="Base directory used to resolve relative slides.pdf_path values.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of existing PDFs to read.",
    )
    parser.add_argument(
        "--page-key",
        action="append",
        default=[],
        help="Restrict to an exact pages.key value. Can be passed multiple times.",
    )
    parser.add_argument(
        "--course-code",
        action="append",
        default=[],
        help="Restrict to a course code segment such as COT105. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-snippets",
        type=int,
        default=20,
        help="Maximum keyword snippets across the whole output.",
    )
    parser.add_argument(
        "--snippets-per-pdf",
        type=int,
        default=3,
        help="Maximum keyword snippets per PDF.",
    )
    parser.add_argument(
        "--snippet-chars",
        type=int,
        default=300,
        help="Maximum characters per keyword context snippet.",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def bounded_context(text: str, start: int, end: int, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    keyword_width = max(0, end - start)
    side = max(0, (max_chars - keyword_width) // 2)
    left = max(0, start - side)
    right = min(len(text), left + max_chars)
    left = max(0, right - max_chars)
    return text[left:right].strip()


def extract_keyword_contexts(
    text: str,
    keywords: tuple[str, ...] = KEYWORDS,
    max_snippets: int = 5,
    snippet_chars: int = 300,
) -> list[dict[str, str]]:
    if max_snippets <= 0 or snippet_chars <= 0:
        return []

    normalized = normalize_text(text)
    lowered = normalized.lower()
    snippets: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for keyword in keywords:
        lowered_keyword = keyword.lower()
        start = 0
        while len(snippets) < max_snippets:
            index = lowered.find(lowered_keyword, start)
            if index < 0:
                break
            snippet = bounded_context(
                normalized,
                index,
                index + len(keyword),
                snippet_chars,
            )
            marker = (keyword, snippet)
            if marker not in seen:
                seen.add(marker)
                snippets.append({"keyword": keyword, "snippet": snippet})
            start = index + max(1, len(lowered_keyword))
        if len(snippets) >= max_snippets:
            break

    return snippets


def extract_deadline_candidates(
    text: str,
    max_candidates: int = 5,
    snippet_chars: int = 120,
) -> list[str]:
    if max_candidates <= 0 or snippet_chars <= 0:
        return []

    normalized = normalize_text(text)
    candidates: list[str] = []
    seen: set[str] = set()
    for pattern in DEADLINE_PATTERNS:
        for match in pattern.finditer(normalized):
            candidate = bounded_context(
                normalized,
                match.start(),
                match.end(),
                snippet_chars,
            )
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def extract_pdf_text_layer(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required to read PDF text layers. Install it with `pip install pypdf` "
            "or add it to requirements after dependency review."
        ) from exc

    reader = PdfReader(str(pdf_path))
    pieces: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text:
            pieces.append(page_text)
    return "\n".join(pieces)


def filter_keys(
    keys: list[str],
    page_keys: list[str],
    course_codes: list[str],
) -> list[str]:
    page_key_filter = set(page_keys)
    course_code_filter = set(course_codes)
    filtered: list[str] = []
    for key in keys:
        parts = key.split("/")
        if page_key_filter and key not in page_key_filter:
            continue
        if course_code_filter and (len(parts) < 2 or parts[1] not in course_code_filter):
            continue
        filtered.append(key)
    return filtered


def fetch_slide_pdf_rows(
    connection: sqlite3.Connection,
    page_keys: list[str],
) -> list[dict[str, Any]]:
    if not page_keys:
        return []

    placeholders = ", ".join("?" for _ in page_keys)
    rows = connection.execute(
        f"""
        SELECT
          p.{quote_identifier("key")} AS page_key,
          s.{quote_identifier("idx")} AS slide_index,
          s.{quote_identifier("pdf_path")} AS pdf_path
        FROM {quote_identifier("pages")} p
        JOIN {quote_identifier("slides")} s
          ON s.{quote_identifier("page_id")} = p.{quote_identifier("id")}
        WHERE p.{quote_identifier("key")} IN ({placeholders})
          AND s.{quote_identifier("pdf_path")} IS NOT NULL
        ORDER BY p.{quote_identifier("key")}, s.{quote_identifier("idx")}, s.{quote_identifier("id")}
        """,
        page_keys,
    ).fetchall()

    return [
        {
            "page_key": str(row[0]),
            "slide_index": int(row[1]),
            "pdf_path": str(row[2]),
        }
        for row in rows
        if str(row[2]).strip()
    ]


def probe_moocs_collect_pdf_text(
    probe_json: Path,
    db_path: Path,
    download_dir: Path,
    limit: int = 10,
    page_keys: list[str] | None = None,
    course_codes: list[str] | None = None,
    max_snippets: int = 20,
    snippets_per_pdf: int = 3,
    snippet_chars: int = 300,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("limit must be zero or greater")
    if max_snippets < 0:
        raise ValueError("max_snippets must be zero or greater")
    if snippets_per_pdf < 0:
        raise ValueError("snippets_per_pdf must be zero or greater")
    if snippet_chars < 0:
        raise ValueError("snippet_chars must be zero or greater")

    resolved_db_path = db_path.expanduser().resolve()
    resolved_download_dir = download_dir.expanduser().resolve()
    aio_pages = load_aio_page_keys(probe_json)
    selected_keys = filter_keys(
        aio_pages["unique_keys"],
        page_keys or [],
        course_codes or [],
    )

    with closing(open_readonly_database(resolved_db_path)) as connection:
        slide_rows = fetch_slide_pdf_rows(connection, selected_keys)

    results: list[dict[str, Any]] = []
    existing_pdf_count = 0
    missing_pdf_count = 0
    total_snippets = 0

    for row in slide_rows:
        if existing_pdf_count >= limit:
            break

        pdf_path = resolve_pdf_path(row["pdf_path"], resolved_db_path, resolved_download_dir)
        if not pdf_path.is_file():
            missing_pdf_count += 1
            continue

        existing_pdf_count += 1
        text = extract_pdf_text_layer(pdf_path)
        remaining_snippets = max(0, max_snippets - total_snippets)
        per_pdf_limit = min(snippets_per_pdf, remaining_snippets)
        keyword_contexts = extract_keyword_contexts(
            text,
            max_snippets=per_pdf_limit,
            snippet_chars=snippet_chars,
        )
        total_snippets += len(keyword_contexts)
        results.append(
            {
                "page_key": row["page_key"],
                "slide_index": row["slide_index"],
                "pdf_file_name": pdf_path.name,
                "text_length": len(text),
                "matched_keywords": sorted(
                    {context["keyword"] for context in keyword_contexts}
                ),
                "keyword_context_snippets": keyword_contexts,
                "deadline_text_candidates": extract_deadline_candidates(text),
            }
        )

    return {
        "probe_json": str(probe_json.expanduser().resolve()),
        "db_path": str(resolved_db_path),
        "download_dir": str(resolved_download_dir),
        "total_aio_pages": aio_pages["generated_key_count"],
        "unique_aio_page_keys": len(aio_pages["unique_keys"]),
        "selected_aio_page_keys": len(selected_keys),
        "matched_slide_pdf_paths": len(slide_rows),
        "processed_existing_pdfs": existing_pdf_count,
        "missing_pdfs_before_limit": missing_pdf_count,
        "total_keyword_snippets": total_snippets,
        "results": results,
        "safety": {
            "pdf_full_text_printed": False,
            "pdf_full_text_saved": False,
            "slide_images_saved": False,
            "raw_svg_saved": False,
            "ocr_used": False,
            "tantivy_index_read": False,
            "sensitive_files_read": False,
        },
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = probe_moocs_collect_pdf_text(
        probe_json=args.probe_json,
        db_path=args.db_path,
        download_dir=args.download_dir,
        limit=args.limit,
        page_keys=args.page_key,
        course_codes=args.course_code,
        max_snippets=args.max_snippets,
        snippets_per_pdf=args.snippets_per_pdf,
        snippet_chars=args.snippet_chars,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
