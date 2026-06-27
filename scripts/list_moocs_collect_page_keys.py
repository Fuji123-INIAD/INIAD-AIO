"""List AIO page keys and MOOCs-Collect slide availability for a course."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_moocs_collect_page_join import (
    open_readonly_database,
    page_url_to_key,
    quote_identifier,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List AIO page_url/page_key rows for a course and show whether "
            "MOOCs-Collect has slides.url and pdf_path values."
        )
    )
    parser.add_argument("probe_json", type=Path, help="Path to AIO probe JSON")
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite")
    parser.add_argument(
        "--course-code",
        required=True,
        help="Course code segment to list, such as COT105.",
    )
    return parser.parse_args()


def iter_page_url_values(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        page_url = value.get("page_url")
        if isinstance(page_url, str) and page_url.strip():
            yield page_url
        for child in value.values():
            yield from iter_page_url_values(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_page_url_values(item)


def load_aio_pages_for_course(probe_json: Path, course_code: str) -> list[dict[str, str]]:
    with probe_json.expanduser().open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    pages: list[dict[str, str]] = []
    seen: set[str] = set()
    for page_url in iter_page_url_values(payload):
        page_key = page_url_to_key(page_url)
        if page_key is None:
            continue
        parts = page_key.split("/")
        if len(parts) < 2 or parts[1] != course_code:
            continue
        if page_key in seen:
            continue
        seen.add(page_key)
        pages.append({"page_key": page_key, "page_url": page_url})
    return pages


def fetch_slide_availability(
    connection: sqlite3.Connection,
    page_keys: list[str],
) -> dict[str, dict[str, Any]]:
    if not page_keys:
        return {}

    placeholders = ", ".join("?" for _ in page_keys)
    rows = connection.execute(
        f"""
        SELECT
          p.{quote_identifier("key")} AS page_key,
          COUNT(s.{quote_identifier("id")}) AS slide_count,
          SUM(
            CASE
              WHEN s.{quote_identifier("url")} IS NOT NULL
               AND TRIM(s.{quote_identifier("url")}) != ''
              THEN 1 ELSE 0
            END
          ) AS slides_url_count,
          SUM(
            CASE
              WHEN s.{quote_identifier("pdf_path")} IS NOT NULL
               AND TRIM(s.{quote_identifier("pdf_path")}) != ''
              THEN 1 ELSE 0
            END
          ) AS pdf_path_count
        FROM {quote_identifier("pages")} p
        LEFT JOIN {quote_identifier("slides")} s
          ON s.{quote_identifier("page_id")} = p.{quote_identifier("id")}
        WHERE p.{quote_identifier("key")} IN ({placeholders})
        GROUP BY p.{quote_identifier("key")}
        """,
        page_keys,
    ).fetchall()

    return {
        str(row[0]): {
            "collect_page_exists": True,
            "slide_count": int(row[1] or 0),
            "slides_url_count": int(row[2] or 0),
            "pdf_path_count": int(row[3] or 0),
        }
        for row in rows
    }


def list_moocs_collect_page_keys(
    probe_json: Path,
    db_path: Path,
    course_code: str,
) -> dict[str, Any]:
    aio_pages = load_aio_pages_for_course(probe_json, course_code)
    page_keys = [page["page_key"] for page in aio_pages]
    resolved_db_path = db_path.expanduser().resolve()

    with closing(open_readonly_database(resolved_db_path)) as connection:
        availability_by_key = fetch_slide_availability(connection, page_keys)

    rows: list[dict[str, Any]] = []
    for page in aio_pages:
        availability = availability_by_key.get(
            page["page_key"],
            {
                "collect_page_exists": False,
                "slide_count": 0,
                "slides_url_count": 0,
                "pdf_path_count": 0,
            },
        )
        rows.append(
            {
                "page_key": page["page_key"],
                "page_url": page["page_url"],
                "collect_page_exists": availability["collect_page_exists"],
                "slide_count": availability["slide_count"],
                "slides_url_exists": availability["slides_url_count"] > 0,
                "slides_url_count": availability["slides_url_count"],
                "pdf_path_exists": availability["pdf_path_count"] > 0,
                "pdf_path_count": availability["pdf_path_count"],
            }
        )

    return {
        "probe_json": str(probe_json.expanduser().resolve()),
        "db_path": str(resolved_db_path),
        "course_code": course_code,
        "page_count": len(rows),
        "collect_page_exists_count": sum(1 for row in rows if row["collect_page_exists"]),
        "slides_url_exists_count": sum(1 for row in rows if row["slides_url_exists"]),
        "pdf_path_exists_count": sum(1 for row in rows if row["pdf_path_exists"]),
        "rows": rows,
        "safety": {
            "db_read_only": True,
            "slide_urls_fetched": False,
            "pdf_text_read": False,
            "html_text_read": False,
            "sensitive_files_read": False,
        },
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = list_moocs_collect_page_keys(
        probe_json=args.probe_json,
        db_path=args.db_path,
        course_code=args.course_code,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
