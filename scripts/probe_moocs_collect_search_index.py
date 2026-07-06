"""Inspect MOOCs-Collect search_index without requiring Tantivy bindings."""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.moocs_collect_text import (
    extract_tantivy_store_texts,
    infer_search_index_engine,
    metadata_from_page_key,
    open_readonly_database,
)


DEFAULT_KEYWORDS = ("セキュリティ", "暗号", "認証", "COT105", "Part1", "情報連携")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe MOOCs-Collect search_index.")
    parser.add_argument(
        "search_index",
        nargs="?",
        type=Path,
        default=default_moocs_collect_root() / "search_index",
    )
    parser.add_argument("--db", type=Path, help="Optional MOOCs-Collect db.sqlite for join checks.")
    parser.add_argument("--keyword", action="append", dest="keywords")
    parser.add_argument("--preview-chars", type=int, default=200)
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args(argv)


def default_moocs_collect_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "me.yu7400ki.moocs-collect"
    return Path.home() / "AppData" / "Roaming" / "me.yu7400ki.moocs-collect"


def probe_moocs_collect_search_index(
    search_index: Path,
    *,
    db_path: Path | None = None,
    keywords: list[str] | None = None,
    preview_chars: int = 200,
    limit: int = 20,
) -> dict[str, Any]:
    resolved = search_index.expanduser().resolve()
    if not resolved.exists():
        return {
            "status": "missing",
            "search_index": str(resolved),
            "exists": False,
            "warnings": [{"message": "search_index path was not found."}],
        }
    if not resolved.is_dir():
        return {
            "status": "error",
            "search_index": str(resolved),
            "exists": True,
            "warnings": [{"message": "search_index path is not a directory."}],
        }

    file_infos = collect_file_infos(resolved)
    engine = infer_search_index_engine(resolved)
    keyword_hits = plain_keyword_hits(
        resolved,
        keywords or list(DEFAULT_KEYWORDS),
        preview_chars=preview_chars,
    )
    stored_documents = []
    join_candidates = []
    if engine == "tantivy":
        extracted = extract_tantivy_store_texts(resolved, limit=limit)
        db_page_keys = load_db_page_keys(db_path) if db_path else set()
        for page_key, text in list(extracted.items())[:limit]:
            parsed = metadata_from_page_key(page_key)
            stored_documents.append(
                {
                    "page_key": page_key,
                    "course_code": parsed.get("course_code"),
                    "lecture_key": parsed.get("lecture_key"),
                    "text_length": len(text),
                    "preview": text[:preview_chars],
                }
            )
            join_candidates.append(
                {
                    "page_key": page_key,
                    "joinable_to_pages_key": page_key in db_page_keys if db_page_keys else None,
                }
            )

    return {
        "status": "ok",
        "search_index": str(resolved),
        "exists": True,
        "file_count": len(file_infos),
        "total_size": sum(item["size"] for item in file_infos),
        "extension_counts": dict(sorted(Counter(item["extension"] for item in file_infos).items())),
        "file_name_patterns": summarize_file_patterns(file_infos),
        "binary_text_distribution": binary_text_distribution(resolved),
        "keyword_hits": keyword_hits[:100],
        "engine_guess": engine,
        "stored_documents": stored_documents,
        "join_candidates": join_candidates,
        "warnings": [],
        "safety": {
            "raw_index_committed": False,
            "preview_chars_max": preview_chars,
        },
    }


def collect_file_infos(root: Path) -> list[dict[str, Any]]:
    infos = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        infos.append(
            {
                "name": path.name,
                "extension": path.suffix.lower() or "(none)",
                "size": size,
            }
        )
    return infos


def summarize_file_patterns(file_infos: list[dict[str, Any]]) -> dict[str, int]:
    patterns: Counter[str] = Counter()
    for info in file_infos:
        name = str(info["name"])
        suffix = str(info["extension"])
        stem = name[:8]
        if len(Path(name).stem) >= 24 and all(char in "0123456789abcdef" for char in Path(name).stem.lower()):
            patterns[f"<hex>{suffix}"] += 1
        elif name.startswith("."):
            patterns[f".<hidden>{suffix}"] += 1
        else:
            patterns[name] += 1
    return dict(sorted(patterns.items()))


def binary_text_distribution(root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            sample = path.read_bytes()[:4096]
        except Exception:
            continue
        if b"\x00" in sample or path.suffix.lower() not in {".json", ".txt"}:
            counts["binary_or_structured"] += 1
        else:
            counts["plain_text"] += 1
    return dict(counts)


def plain_keyword_hits(
    root: Path,
    keywords: list[str],
    *,
    preview_chars: int,
) -> list[dict[str, str]]:
    hits = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            decoded = path.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            continue
        compact = readable_preview_text(decoded)
        for keyword in keywords:
            position = compact.find(keyword)
            if position < 0:
                continue
            start = max(0, position - preview_chars // 2)
            end = min(len(compact), position + len(keyword) + preview_chars // 2)
            hits.append(
                {
                    "keyword": keyword,
                    "path": path.name,
                    "preview": compact[start:end],
                }
            )
    return hits


def load_db_page_keys(db_path: Path | None) -> set[str]:
    if db_path is None:
        return set()


def readable_preview_text(value: str) -> str:
    cleaned = "".join(
        char if (char in "\n\t " or not unicodedata.category(char).startswith("C")) else " "
        for char in value
        if char != "\ufffd"
    )
    return " ".join(cleaned.split())
    try:
        with open_readonly_database(db_path) as connection:
            return {
                str(row[0])
                for row in connection.execute("SELECT key FROM pages WHERE key IS NOT NULL").fetchall()
            }
    except Exception:
        return set()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = probe_moocs_collect_search_index(
        args.search_index,
        db_path=args.db,
        keywords=args.keywords,
        preview_chars=max(0, min(args.preview_chars, 200)),
        limit=max(0, args.limit),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
