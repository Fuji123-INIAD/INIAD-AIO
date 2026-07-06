"""Build MaterialText and MaterialChunk indexes from local providers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.material_chunks import chunk_material_texts
from backend.app.core.material_text import material_texts_from_local_resources
from backend.app.core.moocs_collect_text import load_moocs_collect_material_texts
from backend.app.core.moocs_html_text import load_html_cache_materials


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build data/local MaterialText and MaterialChunk indexes."
    )
    parser.add_argument(
        "--resource-index",
        type=Path,
        default=Path("data/local/resource_index.json"),
        help="Path to AIO local resource_index.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/local/material_text_index.json"),
        help="MaterialText index output path.",
    )
    parser.add_argument(
        "--chunk-output",
        type=Path,
        default=Path("data/local/material_chunk_index.json"),
        help="MaterialChunk index output path.",
    )
    parser.add_argument("--moocs-collect-db", type=Path, help="Path to MOOCs-Collect db.sqlite.")
    parser.add_argument("--moocs-collect-root", type=Path, help="Path to MOOCs-Collect AppData root.")
    parser.add_argument("--search-index", type=Path, help="Path to MOOCs-Collect search_index.")
    parser.add_argument("--include-moocs-collect", action="store_true")
    parser.add_argument("--include-moocs-collect-search-index", action="store_true")
    parser.add_argument("--include-moocs-collect-files", action="store_true")
    parser.add_argument("--include-slide-url-dom", action="store_true")
    parser.add_argument("--include-pdf-ocr", action="store_true")
    parser.add_argument("--include-html-cache", action="store_true")
    parser.add_argument("--html-cache-dir", type=Path, default=Path("data/local/html_cache"))
    parser.add_argument("--include-pdf-cache", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--course-code")
    parser.add_argument("--lecture-key")
    parser.add_argument("--limit", type=int, help="Limit input resources/material rows.")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args(argv)


def build_material_text_index(args: argparse.Namespace) -> dict[str, Any]:
    resources, resource_warnings = load_resource_index(args.resource_index)
    if args.limit is not None:
        resources = resources[: max(0, args.limit)]
    warnings = list(resource_warnings)
    materials = material_texts_from_local_resources(
        resources,
        index_path=args.resource_index,
        include_text_cache=bool(args.include_pdf_cache),
        base_url=args.base_url,
    )

    if args.include_moocs_collect:
        if args.moocs_collect_db is None:
            warnings.append({"message": "--include-moocs-collect requires --moocs-collect-db."})
        else:
            collect_materials, collect_warnings = load_moocs_collect_material_texts(
                args.moocs_collect_db,
                local_resources=resources,
                limit=args.limit,
                moocs_collect_root=args.moocs_collect_root,
                search_index=args.search_index,
                include_search_index=bool(
                    args.include_moocs_collect or args.include_moocs_collect_search_index
                ),
                include_appdata_files=bool(args.include_moocs_collect_files),
                include_slide_url_dom=bool(args.include_slide_url_dom),
                include_pdf_native=True,
                include_pdf_ocr=bool(args.include_pdf_ocr),
                course_code=args.course_code,
                lecture_key=args.lecture_key,
                debug=bool(args.debug),
            )
            materials.extend(collect_materials)
            warnings.extend(collect_warnings)

    if args.include_html_cache:
        html_materials, html_warnings = load_html_cache_materials(args.html_cache_dir)
        materials.extend(html_materials)
        warnings.extend(html_warnings)

    chunks = chunk_material_texts(materials)
    write_json(
        args.output,
        {
            "status": "ok",
            "materials": [material.to_dict(include_text=True) for material in materials],
            "material_count": len(materials),
            "warnings": warnings,
        },
    )
    write_json(
        args.chunk_output,
        {
            "status": "ok",
            "chunks": [chunk.to_dict() for chunk in chunks],
            "chunk_count": len(chunks),
            "warnings": warnings,
        },
    )
    return {
        "status": "ok",
        "resource_count": len(resources),
        "material_count": len(materials),
        "chunk_count": len(chunks),
        "output": str(args.output),
        "chunk_output": str(args.chunk_output),
        "warnings": warnings if args.debug else warnings[:5],
        "safety": {
            "writes_under_data_local_by_default": True,
            "moocs_collect_db_read_only": bool(args.include_moocs_collect),
            "raw_credentials_read": False,
        },
    }


def load_resource_index(index_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    resolved = index_path.expanduser()
    if not resolved.exists():
        return [], [{"message": f"resource_index.json not found: {resolved}"}]
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [{"message": f"Could not read resource index: {exc}"}]
    resources = payload.get("resources")
    if not isinstance(resources, list):
        return [], [{"message": "resource_index.json resources must be an array."}]
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    return [resource for resource in resources if isinstance(resource, dict)], warnings


def write_json(path: Path, payload: dict[str, Any]) -> None:
    resolved = path.expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = build_material_text_index(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
