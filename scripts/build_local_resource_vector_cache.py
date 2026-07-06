"""Build deterministic local vectors for LocalResource context cards."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.context_cards import build_local_resource_card
from backend.app.core.embeddings import build_vector_cache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a local vector cache from resource_index.json context cards."
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("data/local/resource_index.json"),
        help="Input local resource index.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/local/resource_vectors.json"),
        help="Output vector cache path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = json.loads(args.index.read_text(encoding="utf-8"))
    resources = data.get("resources", [])
    documents = []
    for resource in resources if isinstance(resources, list) else []:
        if not isinstance(resource, dict):
            continue
        card_text = str(resource.get("card_text") or build_local_resource_card(resource))
        documents.append(
            {
                "id": resource.get("resource_id"),
                "text": card_text,
            }
        )

    cache = build_vector_cache(documents)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "document_count": len(documents),
                "provider": cache["provider"],
                "dimensions": cache["dimensions"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
