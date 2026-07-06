"""Build an AIO local resource_index.json from a local resource root."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.local_resources import (
    build_local_resource_index,
    write_local_resource_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover local PDFs under a MOOCs-Collect directory and write "
            "data/local/resource_index.json for later MCP preparation."
        )
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Root directory to scan recursively for local PDFs.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output resource_index.json path.",
    )
    parser.add_argument(
        "--extract-text",
        action="store_true",
        help="Extract PDF text layers and write local text cache JSON files.",
    )
    parser.add_argument(
        "--text-cache-dir",
        type=Path,
        default=Path("data/local/text_cache"),
        help="Directory for extracted PDF text cache JSON files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = build_local_resource_index(
        args.root,
        extract_text=args.extract_text,
        text_cache_dir=args.text_cache_dir,
        text_cache_path_base=args.output.parent if args.extract_text else None,
    )
    write_local_resource_index(index, args.output)
    print(json.dumps(index.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
