"""Safely inspect MOOCs-Collect AppData file layout."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.moocs_collect_text import has_sensitive_path


INTERESTING_EXTENSIONS = {".json", ".html", ".htm", ".svg", ".txt", ".md", ".cache", ".db", ".sqlite", ".pdf"}
INTERESTING_PATH_WORDS = (
    "search",
    "index",
    "cache",
    "slides",
    "pdf",
    "asset",
    "store",
    "tantivy",
    "meili",
    "lunr",
    "orama",
)
DEFAULT_KEYWORDS = ("セキュリティ", "暗号", "認証", "COT105", "Part1", "情報連携")
TEXT_EXTENSIONS = {".json", ".html", ".htm", ".svg", ".txt", ".md", ".cache"}
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe MOOCs-Collect AppData files.")
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=default_moocs_collect_root(),
        help="MOOCs-Collect AppData root.",
    )
    parser.add_argument("--keyword", action="append", dest="keywords")
    parser.add_argument("--preview-chars", type=int, default=200)
    return parser.parse_args(argv)


def default_moocs_collect_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "me.yu7400ki.moocs-collect"
    return Path.home() / "AppData" / "Roaming" / "me.yu7400ki.moocs-collect"


def probe_moocs_collect_files(
    root: Path,
    *,
    keywords: list[str] | None = None,
    preview_chars: int = 200,
) -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    warnings: list[dict[str, str]] = []
    if not resolved.exists():
        return {
            "status": "missing",
            "root": str(resolved),
            "directory_candidates": [],
            "extension_counts": {},
            "extension_total_sizes": {},
            "keyword_hits": [],
            "possible_text_sources": [],
            "warnings": [{"message": "MOOCs-Collect AppData root was not found."}],
        }
    if not resolved.is_dir():
        return {
            "status": "error",
            "root": str(resolved),
            "warnings": [{"message": "Root is not a directory."}],
        }

    extension_counts: Counter[str] = Counter()
    extension_sizes: Counter[str] = Counter()
    directory_candidates = []
    keyword_hits = []
    possible_text_sources = []
    keyword_values = keywords or list(DEFAULT_KEYWORDS)
    file_count = 0
    root_directories = []
    interesting_file_presence = {ext: False for ext in sorted(INTERESTING_EXTENSIONS)}

    for child in sorted(resolved.iterdir()):
        if child.is_dir():
            root_directories.append(child.name)

    for path in resolved.rglob("*"):
        relative = safe_relative(path, resolved)
        lowered = str(relative).lower()
        if path.is_dir():
            reasons = [
                f"name contains {word}"
                for word in INTERESTING_PATH_WORDS
                if word in lowered
            ]
            if reasons:
                directory_candidates.append({"path": str(relative), "reason": "; ".join(reasons)})
            continue
        if not path.is_file():
            continue
        file_count += 1
        suffix = path.suffix.lower()
        extension_counts[suffix or "(none)"] += 1
        try:
            extension_sizes[suffix or "(none)"] += path.stat().st_size
        except OSError:
            pass
        if suffix in interesting_file_presence:
            interesting_file_presence[suffix] = True
        if has_sensitive_path(path) or suffix not in TEXT_EXTENSIONS:
            continue
        text = read_text_preview(path, max_chars=20000)
        if not text:
            continue
        compact = compact_text(text)
        if JAPANESE_RE.search(compact):
            possible_text_sources.append(
                {
                    "path": str(relative),
                    "reason": "contains Japanese text",
                    "preview": compact[:preview_chars],
                }
            )
        for keyword in keyword_values:
            position = compact.find(keyword)
            if position < 0:
                continue
            start = max(0, position - preview_chars // 2)
            end = min(len(compact), position + len(keyword) + preview_chars // 2)
            keyword_hits.append(
                {
                    "keyword": keyword,
                    "path": str(relative),
                    "preview": compact[start:end],
                }
            )

    return {
        "status": "ok",
        "root": str(resolved),
        "root_directories": root_directories,
        "file_count": file_count,
        "directory_candidates": directory_candidates[:100],
        "extension_counts": dict(sorted(extension_counts.items())),
        "extension_total_sizes": dict(sorted(extension_sizes.items())),
        "interesting_extension_presence": interesting_file_presence,
        "keyword_hits": keyword_hits[:100],
        "possible_text_sources": possible_text_sources[:100],
        "warnings": warnings,
        "safety": {
            "pdf_or_image_text_read": False,
            "sensitive_files_read": False,
            "preview_chars_max": preview_chars,
        },
    }


def read_text_preview(path: Path, *, max_chars: int) -> str:
    try:
        data = path.read_bytes()[: max_chars * 4]
    except Exception:
        return ""
    if not data or data.count(b"\x00") > max(4, len(data) // 20):
        return ""
    return data.decode("utf-8", errors="ignore")[:max_chars]


def safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def compact_text(value: str) -> str:
    return " ".join(str(value or "").split())


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = probe_moocs_collect_files(
        args.root,
        keywords=args.keywords,
        preview_chars=max(0, min(args.preview_chars, 200)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
