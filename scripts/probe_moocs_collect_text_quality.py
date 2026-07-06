"""Probe MOOCs-Collect DB text quality without committing extracted content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_material_text_index import load_resource_index
from backend.app.core.moocs_collect_text import inspect_moocs_collect_text_quality


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect whether MOOCs-Collect slide text can feed AIO MaterialText."
    )
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite.")
    parser.add_argument(
        "--resource-index",
        type=Path,
        default=Path("data/local/resource_index.json"),
        help="Optional AIO resource index for LocalResource join checks.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--preview-chars", type=int, default=160)
    parser.add_argument("--moocs-collect-root", type=Path)
    parser.add_argument("--search-index", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    resources, warnings = load_resource_index(args.resource_index)
    report = inspect_moocs_collect_text_quality(
        args.db_path,
        local_resources=resources,
        limit=args.limit,
        preview_chars=args.preview_chars,
        moocs_collect_root=args.moocs_collect_root,
        search_index=args.search_index,
    )
    report["warnings"] = [*warnings, *report.get("warnings", [])]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
