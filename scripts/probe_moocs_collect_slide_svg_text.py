"""Probe short snippets from Google Slides embed SVG aria-label text."""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_moocs_collect_page_join import (
    load_aio_page_keys,
    open_readonly_database,
    quote_identifier,
)
from scripts.probe_moocs_collect_pdf_text import (
    extract_deadline_candidates,
    extract_keyword_contexts,
    filter_keys,
)


class SvgAriaLabelParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.labels: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "g":
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if attr_map.get("role") == "img" and attr_map.get("aria-label"):
            self.labels.append(attr_map["aria-label"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Google Slides embed HTML for MOOCs-Collect slide URLs, extract "
            "SVG g[role=img][aria-label] text, and print bounded snippets only."
        )
    )
    parser.add_argument("probe_json", type=Path, help="Path to AIO probe JSON")
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite")
    parser.add_argument(
        "--course-code",
        action="append",
        default=[],
        help="Restrict to a course code segment such as COT105. Can be passed multiple times.",
    )
    parser.add_argument(
        "--page-key",
        action="append",
        default=[],
        help="Restrict to an exact pages.key value. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of slide URLs to fetch.",
    )
    parser.add_argument(
        "--max-snippets",
        type=int,
        default=20,
        help="Maximum keyword snippets across the whole output.",
    )
    parser.add_argument(
        "--snippets-per-slide",
        type=int,
        default=3,
        help="Maximum keyword snippets per slide URL.",
    )
    parser.add_argument(
        "--snippet-chars",
        type=int,
        default=300,
        help="Maximum characters per keyword context snippet.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout seconds for each embed URL.",
    )
    return parser.parse_args()


def decode_possible_escaped_svg_text(value: str) -> str:
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


def extract_svg_fragments(embed_html: str) -> list[str]:
    decoded = decode_possible_escaped_svg_text(embed_html)
    return re.findall(r"<svg\b.*?</svg>", decoded, flags=re.IGNORECASE | re.DOTALL)


def extract_aria_labels_from_svg(svg_text: str) -> list[str]:
    parser = SvgAriaLabelParser()
    parser.feed(svg_text)
    return [label.strip() for label in parser.labels if label.strip()]


def extract_aria_labels_from_embed_html(embed_html: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for svg in extract_svg_fragments(embed_html):
        for label in extract_aria_labels_from_svg(svg):
            if label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def fetch_slide_url_rows(
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
          s.{quote_identifier("url")} AS slide_url
        FROM {quote_identifier("pages")} p
        JOIN {quote_identifier("slides")} s
          ON s.{quote_identifier("page_id")} = p.{quote_identifier("id")}
        WHERE p.{quote_identifier("key")} IN ({placeholders})
          AND s.{quote_identifier("url")} IS NOT NULL
        ORDER BY p.{quote_identifier("key")}, s.{quote_identifier("idx")}, s.{quote_identifier("id")}
        """,
        page_keys,
    ).fetchall()

    return [
        {
            "page_key": str(row[0]),
            "slide_index": int(row[1]),
            "slide_url": str(row[2]),
        }
        for row in rows
        if str(row[2]).strip()
    ]


def fetch_embed_html(slide_url: str, timeout: float) -> str:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "requests is required to fetch Google Slides embed HTML."
        ) from exc

    response = requests.get(slide_url, timeout=timeout)
    response.raise_for_status()
    return response.text


def probe_moocs_collect_slide_svg_text(
    probe_json: Path,
    db_path: Path,
    course_codes: list[str] | None = None,
    page_keys: list[str] | None = None,
    limit: int = 5,
    max_snippets: int = 20,
    snippets_per_slide: int = 3,
    snippet_chars: int = 300,
    timeout: float = 20.0,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("limit must be zero or greater")
    if max_snippets < 0:
        raise ValueError("max_snippets must be zero or greater")
    if snippets_per_slide < 0:
        raise ValueError("snippets_per_slide must be zero or greater")
    if snippet_chars < 0:
        raise ValueError("snippet_chars must be zero or greater")

    resolved_db_path = db_path.expanduser().resolve()
    aio_pages = load_aio_page_keys(probe_json)
    selected_keys = filter_keys(
        aio_pages["unique_keys"],
        page_keys or [],
        course_codes or [],
    )

    with closing(open_readonly_database(resolved_db_path)) as connection:
        slide_rows = fetch_slide_url_rows(connection, selected_keys)

    results: list[dict[str, Any]] = []
    fetch_errors: list[dict[str, str]] = []
    total_snippets = 0

    for row in slide_rows[:limit]:
        try:
            embed_html = fetch_embed_html(row["slide_url"], timeout)
        except Exception as exc:
            fetch_errors.append(
                {
                    "page_key": row["page_key"],
                    "slide_index": str(row["slide_index"]),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        labels = extract_aria_labels_from_embed_html(embed_html)
        slide_text = "\n".join(labels)
        remaining_snippets = max(0, max_snippets - total_snippets)
        per_slide_limit = min(snippets_per_slide, remaining_snippets)
        keyword_contexts = extract_keyword_contexts(
            slide_text,
            max_snippets=per_slide_limit,
            snippet_chars=snippet_chars,
        )
        total_snippets += len(keyword_contexts)
        results.append(
            {
                "page_key": row["page_key"],
                "slide_index": row["slide_index"],
                "slide_url_host": _url_host(row["slide_url"]),
                "aria_label_count": len(labels),
                "text_length": len(slide_text),
                "matched_keywords": sorted(
                    {context["keyword"] for context in keyword_contexts}
                ),
                "keyword_context_snippets": keyword_contexts,
                "deadline_text_candidates": extract_deadline_candidates(slide_text),
            }
        )

    return {
        "probe_json": str(probe_json.expanduser().resolve()),
        "db_path": str(resolved_db_path),
        "total_aio_pages": aio_pages["generated_key_count"],
        "unique_aio_page_keys": len(aio_pages["unique_keys"]),
        "selected_aio_page_keys": len(selected_keys),
        "matched_slide_urls": len(slide_rows),
        "fetched_slide_urls": len(results),
        "fetch_error_count": len(fetch_errors),
        "fetch_errors": fetch_errors[:5],
        "total_keyword_snippets": total_snippets,
        "results": results,
        "safety": {
            "embed_html_full_text_printed": False,
            "embed_html_saved": False,
            "raw_svg_printed": False,
            "raw_svg_saved": False,
            "slide_images_saved": False,
            "slide_full_text_printed": False,
            "sensitive_files_read": False,
        },
    }


def _url_host(url: str) -> str:
    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url)
    return match.group(1) if match else ""


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = probe_moocs_collect_slide_svg_text(
        probe_json=args.probe_json,
        db_path=args.db_path,
        course_codes=args.course_code,
        page_keys=args.page_key,
        limit=args.limit,
        max_snippets=args.max_snippets,
        snippets_per_slide=args.snippets_per_slide,
        snippet_chars=args.snippet_chars,
        timeout=args.timeout,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
