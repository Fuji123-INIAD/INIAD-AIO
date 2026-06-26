"""Inspect local MOOCs-Collect desktop artifacts without reading course content."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any


COUNT_TABLES = ("courses", "lectures", "pages", "slides")
SENSITIVE_NAME_PARTS = (
    "store.json",
    "keyring",
    "cookie",
    "token",
    "password",
    "storage_state",
)


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a MOOCs-Collect desktop db.sqlite, search_index directory, "
            "and downloaded PDF presence without printing lecture or PDF text."
        )
    )
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite")
    parser.add_argument(
        "--search-index",
        type=Path,
        help="Optional path to the MOOCs-Collect search_index directory.",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        help="Optional base directory used to resolve relative slides.pdf_path values.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="Maximum number of safe samples to print for pages.key and PDF file names.",
    )
    return parser.parse_args()


def open_readonly_database(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"db.sqlite not found: {resolved}")
    return sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)


def has_sensitive_name(path: Path) -> bool:
    lowered_parts = [part.lower() for part in path.parts]
    return any(
        sensitive in part
        for part in lowered_parts
        for sensitive in SENSITIVE_NAME_PARTS
    )


def list_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def table_columns(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = connection.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
    return [
        {
            "name": row[1],
            "type": row[2],
            "notnull": bool(row[3]),
            "primary_key": bool(row[5]),
        }
        for row in rows
    ]


def inspect_schema(connection: sqlite3.Connection) -> dict[str, Any]:
    tables = list_tables(connection)
    return {
        "tables": tables,
        "columns": {table: table_columns(connection, table) for table in tables},
    }


def inspect_counts(connection: sqlite3.Connection) -> dict[str, int | None]:
    tables = set(list_tables(connection))
    counts: dict[str, int | None] = {}
    for table in COUNT_TABLES:
        if table in tables:
            counts[table] = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {quote_identifier(table)}"
                ).fetchone()[0]
            )
        else:
            counts[table] = None
    return counts


def column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {column["name"] for column in table_columns(connection, table)}


def inspect_page_keys(
    connection: sqlite3.Connection, sample_limit: int
) -> dict[str, Any]:
    tables = set(list_tables(connection))
    if "pages" not in tables:
        return {"available": False, "samples": []}

    columns = column_names(connection, "pages")
    selectable = [name for name in ("key", "slug") if name in columns]
    if not selectable:
        return {"available": False, "samples": []}

    select_sql = ", ".join(quote_identifier(name) for name in selectable)
    rows = connection.execute(
        f"SELECT {select_sql} FROM {quote_identifier('pages')} LIMIT ?",
        (max(0, sample_limit),),
    ).fetchall()
    return {
        "available": True,
        "columns": selectable,
        "samples": [
            {name: row[index] for index, name in enumerate(selectable)} for row in rows
        ],
    }


def resolve_pdf_path(raw_path: str, db_path: Path, download_dir: Path | None) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    if download_dir is not None:
        return download_dir / path
    return db_path.resolve().parent / path


def inspect_slide_pdfs(
    connection: sqlite3.Connection,
    db_path: Path,
    download_dir: Path | None,
    sample_limit: int,
) -> dict[str, Any]:
    tables = set(list_tables(connection))
    if "slides" not in tables or "pdf_path" not in column_names(connection, "slides"):
        return {
            "available": False,
            "total": None,
            "null": None,
            "non_null": None,
            "existing": None,
            "missing": None,
            "existing_ratio_of_non_null": None,
            "existing_ratio_of_total": None,
            "extensions": {},
            "filename_samples": [],
        }

    rows = connection.execute(
        f"SELECT {quote_identifier('pdf_path')} FROM {quote_identifier('slides')}"
    ).fetchall()
    null_count = 0
    existing_count = 0
    missing_count = 0
    extensions: Counter[str] = Counter()
    filename_samples: list[str] = []

    for (raw_pdf_path,) in rows:
        if raw_pdf_path is None or str(raw_pdf_path).strip() == "":
            null_count += 1
            continue

        raw_text = str(raw_pdf_path)
        extensions[Path(raw_text).suffix.lower() or "(none)"] += 1
        resolved = resolve_pdf_path(raw_text, db_path, download_dir)
        if resolved.is_file():
            existing_count += 1
        else:
            missing_count += 1

        if len(filename_samples) < sample_limit:
            filename_samples.append(resolved.name)

    total_count = len(rows)
    non_null_count = total_count - null_count
    return {
        "available": True,
        "total": total_count,
        "null": null_count,
        "non_null": non_null_count,
        "existing": existing_count,
        "missing": missing_count,
        "existing_ratio_of_non_null": (
            existing_count / non_null_count if non_null_count else None
        ),
        "existing_ratio_of_total": existing_count / total_count if total_count else None,
        "extensions": dict(sorted(extensions.items())),
        "filename_samples": filename_samples,
    }


def inspect_search_index(search_index: Path | None) -> dict[str, Any]:
    if search_index is None:
        return {"provided": False, "exists": None, "file_count": None, "total_size": None}

    resolved = search_index.expanduser().resolve()
    if has_sensitive_name(resolved):
        return {
            "provided": True,
            "path": str(resolved),
            "exists": resolved.exists(),
            "skipped": True,
            "reason": "path name looks sensitive",
            "file_count": None,
            "total_size": None,
        }
    if not resolved.is_dir():
        return {
            "provided": True,
            "path": str(resolved),
            "exists": resolved.exists(),
            "file_count": 0,
            "total_size": 0,
        }

    file_count = 0
    total_size = 0
    for child in resolved.rglob("*"):
        if child.is_file():
            file_count += 1
            total_size += child.stat().st_size

    return {
        "provided": True,
        "path": str(resolved),
        "exists": True,
        "file_count": file_count,
        "total_size": total_size,
    }


def inspect_moocs_collect_local(
    db_path: Path,
    search_index: Path | None = None,
    download_dir: Path | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    if sample_limit < 0:
        raise ValueError("sample_limit must be zero or greater")

    resolved_db_path = db_path.expanduser().resolve()
    with closing(open_readonly_database(resolved_db_path)) as connection:
        connection.row_factory = sqlite3.Row
        schema = inspect_schema(connection)
        return {
            "db_path": str(resolved_db_path),
            "db_exists": True,
            "schema": schema,
            "counts": inspect_counts(connection),
            "pages": inspect_page_keys(connection, sample_limit),
            "slides_pdf_path": inspect_slide_pdfs(
                connection,
                resolved_db_path,
                download_dir.expanduser().resolve() if download_dir is not None else None,
                sample_limit,
            ),
            "search_index": inspect_search_index(search_index),
            "safety": {
                "pdf_text_read": False,
                "lecture_text_printed": False,
                "sensitive_files_read": False,
            },
        }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = inspect_moocs_collect_local(
        db_path=args.db_path,
        search_index=args.search_index,
        download_dir=args.download_dir,
        sample_limit=args.sample_limit,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
