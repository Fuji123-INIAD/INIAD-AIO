"""Check whether AIO MOOCs page_url values join to MOOCs-Collect pages.key."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare AIO probe page_url values with MOOCs-Collect pages.key "
            "without reading PDF, HTML, slide, index, or credential content."
        )
    )
    parser.add_argument("probe_json", type=Path, help="Path to AIO probe JSON")
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite")
    parser.add_argument(
        "--download-dir",
        type=Path,
        help="Optional base directory used to resolve relative slides.pdf_path values.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Maximum number of matched/unmatched key samples to print.",
    )
    return parser.parse_args()


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


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


def iter_page_urls(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        page_url = value.get("page_url")
        if isinstance(page_url, str) and page_url.strip():
            yield page_url
        for child in value.values():
            yield from iter_page_urls(child)
    elif isinstance(value, list):
        for item in value:
            yield from iter_page_urls(item)


def load_aio_page_keys(probe_json: Path) -> dict[str, Any]:
    with probe_json.expanduser().open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    page_urls = list(iter_page_urls(payload))
    generated_keys: list[str] = []
    invalid_page_urls = 0
    seen: set[str] = set()
    unique_keys: list[str] = []

    for page_url in page_urls:
        key = page_url_to_key(page_url)
        if key is None:
            invalid_page_urls += 1
            continue
        generated_keys.append(key)
        if key not in seen:
            seen.add(key)
            unique_keys.append(key)

    return {
        "total_page_urls": len(page_urls),
        "generated_key_count": len(generated_keys),
        "invalid_page_urls": invalid_page_urls,
        "unique_keys": unique_keys,
    }


def resolve_pdf_path(raw_path: str, db_path: Path, download_dir: Path | None) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    if download_dir is not None:
        return download_dir / path
    return db_path.resolve().parent / path


def fetch_collect_page_ids(
    connection: sqlite3.Connection, page_keys: list[str]
) -> dict[str, list[int]]:
    if not page_keys:
        return {}

    placeholders = ", ".join("?" for _ in page_keys)
    rows = connection.execute(
        f"""
        SELECT {quote_identifier("key")}, {quote_identifier("id")}
        FROM {quote_identifier("pages")}
        WHERE {quote_identifier("key")} IN ({placeholders})
        """,
        page_keys,
    ).fetchall()

    page_ids_by_key: dict[str, list[int]] = {}
    for key, page_id in rows:
        page_ids_by_key.setdefault(str(key), []).append(int(page_id))
    return page_ids_by_key


def inspect_matched_slides(
    connection: sqlite3.Connection,
    db_path: Path,
    download_dir: Path | None,
    page_ids: list[int],
) -> dict[str, int]:
    if not page_ids:
        return {
            "matched_slides_count": 0,
            "matched_slides_with_pdf_path_count": 0,
            "matched_slides_existing_pdf_count": 0,
        }

    placeholders = ", ".join("?" for _ in page_ids)
    rows = connection.execute(
        f"""
        SELECT {quote_identifier("pdf_path")}
        FROM {quote_identifier("slides")}
        WHERE {quote_identifier("page_id")} IN ({placeholders})
        """,
        page_ids,
    ).fetchall()

    with_pdf_path = 0
    existing_pdf = 0
    for (raw_pdf_path,) in rows:
        if raw_pdf_path is None or str(raw_pdf_path).strip() == "":
            continue
        with_pdf_path += 1
        resolved = resolve_pdf_path(str(raw_pdf_path), db_path, download_dir)
        if resolved.is_file():
            existing_pdf += 1

    return {
        "matched_slides_count": len(rows),
        "matched_slides_with_pdf_path_count": with_pdf_path,
        "matched_slides_existing_pdf_count": existing_pdf,
    }


def check_moocs_collect_page_join(
    probe_json: Path,
    db_path: Path,
    download_dir: Path | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    if sample_limit < 0:
        raise ValueError("sample_limit must be zero or greater")

    resolved_db_path = db_path.expanduser().resolve()
    resolved_download_dir = (
        download_dir.expanduser().resolve() if download_dir is not None else None
    )
    aio_pages = load_aio_page_keys(probe_json)
    unique_keys = aio_pages["unique_keys"]

    with closing(open_readonly_database(resolved_db_path)) as connection:
        page_ids_by_key = fetch_collect_page_ids(connection, unique_keys)
        matched_keys = [key for key in unique_keys if key in page_ids_by_key]
        unmatched_keys = [key for key in unique_keys if key not in page_ids_by_key]
        matched_page_ids = [
            page_id for key in matched_keys for page_id in page_ids_by_key[key]
        ]
        slide_summary = inspect_matched_slides(
            connection,
            resolved_db_path,
            resolved_download_dir,
            matched_page_ids,
        )

    unique_key_count = len(unique_keys)
    matched_key_count = len(matched_keys)
    return {
        "probe_json": str(probe_json.expanduser().resolve()),
        "db_path": str(resolved_db_path),
        "download_dir": (
            str(resolved_download_dir) if resolved_download_dir is not None else None
        ),
        "total_aio_pages": aio_pages["generated_key_count"],
        "total_aio_page_urls": aio_pages["total_page_urls"],
        "invalid_page_urls": aio_pages["invalid_page_urls"],
        "unique_aio_page_keys": unique_key_count,
        "matched_keys_count": matched_key_count,
        "unmatched_keys_count": len(unmatched_keys),
        "match_ratio": matched_key_count / unique_key_count if unique_key_count else None,
        **slide_summary,
        "unmatched_key_samples": unmatched_keys[:sample_limit],
        "matched_key_samples": matched_keys[:sample_limit],
        "safety": {
            "pdf_text_read": False,
            "slide_text_read": False,
            "html_text_read": False,
            "tantivy_index_read": False,
            "sensitive_files_read": False,
        },
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = check_moocs_collect_page_join(
        probe_json=args.probe_json,
        db_path=args.db_path,
        download_dir=args.download_dir,
        sample_limit=args.sample_limit,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
