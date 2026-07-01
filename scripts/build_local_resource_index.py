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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    index = build_local_resource_index(args.root)
    write_local_resource_index(index, args.output)
    print(json.dumps(index.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
