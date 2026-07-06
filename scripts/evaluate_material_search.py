"""Evaluate material search ranking with a small fixture.

This script intentionally uses synthetic chunks only. It does not read
`data/local`, MOOCs-Collect AppData, PDFs, search indexes, or lecture text dumps.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.context_pack import MATERIAL_SEARCH_CAUTION
from backend.app.core.material_chunks import MaterialChunk
from backend.app.core.material_search import search_context_pack, search_material_chunks


DEFAULT_QUERY = "security"
DEFAULT_FILTERS = {
    "course_code": "COT105",
    "course_title": "Info Link I",
    "lecture_key": "08",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate MaterialChunk search ranking on synthetic fixtures."
    )
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args(argv)


def build_fixture_chunks() -> list[MaterialChunk]:
    return [
        fixture_chunk(
            chunk_id="broad-text",
            material_id="broad-material",
            course_title="Info Link I Advanced",
            lecture_key="08-extra",
            title="Broad security",
            text="security overview with broad lecture metadata",
            source_label="A broad matching lecture",
            source_type="moocs_collect_search_index",
            provider="moocs_collect_search_index",
            extraction_method="search_index",
        ),
        fixture_chunk(
            chunk_id="exact-text-1",
            material_id="exact-material",
            course_title="Info Link I",
            lecture_key="08",
            title="Exact security part 1",
            text="security authentication and access control from search index",
            source_label="Z exact lecture part 1",
            source_type="moocs_collect_search_index",
            provider="moocs_collect_search_index",
            extraction_method="search_index",
        ),
        fixture_chunk(
            chunk_id="exact-text-2",
            material_id="exact-material",
            course_title="Info Link I",
            lecture_key="08",
            title="Exact security part 2",
            text="security cryptography and authentication from the same material",
            source_label="Z exact lecture part 2",
            source_type="moocs_collect_search_index",
            provider="moocs_collect_search_index",
            extraction_method="search_index",
        ),
        fixture_chunk(
            chunk_id="metadata-only",
            material_id="metadata-material",
            course_title="Info Link I",
            lecture_key="08",
            title="Security metadata PDF",
            text="COT105 Info Link I 08 security PDF metadata only",
            source_label="Metadata fallback PDF",
            source_type="pdf_metadata",
            provider="moocs_collect_db_metadata",
            extraction_method="metadata_only",
            chunk_type="metadata",
        ),
    ]


def fixture_chunk(
    *,
    chunk_id: str,
    material_id: str,
    course_title: str,
    lecture_key: str,
    title: str,
    text: str,
    source_label: str,
    source_type: str,
    provider: str,
    extraction_method: str,
    chunk_type: str = "slide",
) -> MaterialChunk:
    return MaterialChunk(
        chunk_id=chunk_id,
        material_id=material_id,
        course_code="COT105",
        course_title=course_title,
        lecture_key=lecture_key,
        lecture_title="Security",
        title=title,
        chunk_index=0,
        chunk_type=chunk_type,
        text=text,
        text_length=len(text),
        source_label=source_label,
        open_url="http://127.0.0.1:8000/materials/demo.pdf",
        source_type=source_type,
        provider=provider,
        extraction_method=extraction_method,
        local_resource_id=None,
        ontology_tags=["material", chunk_type, source_type, provider, "COT105", lecture_key],
        warnings=[],
    )


def evaluate_search_quality(
    *,
    query: str = DEFAULT_QUERY,
    mode: str = "hybrid",
    limit: int = 5,
) -> dict[str, Any]:
    chunks = build_fixture_chunks()
    results = search_material_chunks(
        chunks,
        query=query,
        mode=mode,
        limit=limit,
        filters=DEFAULT_FILTERS,
    )
    context = search_context_pack(
        chunks,
        query=query,
        mode=mode,
        limit=limit,
        filters=DEFAULT_FILTERS,
    )
    checks = [
        check_exact_filter_boost(results),
        check_text_above_metadata(results),
        check_duplicate_material_suppression(results),
        check_source_metadata_preserved(results),
        check_caution_preserved(context),
    ]
    return {
        "status": "ok" if all(check["passed"] for check in checks) else "fail",
        "query": query,
        "mode": mode,
        "filters": DEFAULT_FILTERS,
        "checks": checks,
        "top_results": [
            summarize_result(result, rank=index)
            for index, result in enumerate(results, start=1)
        ],
    }


def check_exact_filter_boost(results: list[dict[str, Any]]) -> dict[str, Any]:
    top = results[0] if results else {}
    return {
        "name": "exact_course_title_and_lecture_key_boost",
        "passed": (
            top.get("material_id") == "exact-material"
            and top.get("course_title") == "Info Link I"
            and top.get("lecture_key") == "08"
        ),
        "detail": (
            f"top={top.get('chunk_id')}, "
            f"course_title={top.get('course_title')}, lecture_key={top.get('lecture_key')}"
        ),
    }


def check_text_above_metadata(results: list[dict[str, Any]]) -> dict[str, Any]:
    first_metadata = first_index(results, lambda item: item.get("chunk_type") == "metadata")
    text_indexes = [
        index
        for index, item in enumerate(results)
        if item.get("chunk_type") != "metadata"
    ]
    passed = bool(text_indexes) and (
        first_metadata is None or max(text_indexes) < first_metadata
    )
    return {
        "name": "text_chunk_above_metadata_only",
        "passed": passed,
        "detail": f"text_indexes={text_indexes}, first_metadata={first_metadata}",
    }


def check_duplicate_material_suppression(results: list[dict[str, Any]]) -> dict[str, Any]:
    first_materials = [str(result.get("material_id")) for result in results[:2]]
    return {
        "name": "same_material_not_repeated_in_top_two",
        "passed": len(first_materials) == len(set(first_materials)),
        "detail": f"top_two_materials={first_materials}",
    }


def check_source_metadata_preserved(results: list[dict[str, Any]]) -> dict[str, Any]:
    top = results[0] if results else {}
    required = ("provider", "source_type", "extraction_method")
    return {
        "name": "provider_source_type_method_preserved",
        "passed": all(top.get(key) for key in required),
        "detail": ", ".join(f"{key}={top.get(key)}" for key in required),
    }


def check_caution_preserved(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "context_caution_preserved",
        "passed": context.get("caution") == MATERIAL_SEARCH_CAUTION,
        "detail": "present" if context.get("caution") else "missing",
    }


def first_index(results: list[dict[str, Any]], predicate: Any) -> int | None:
    for index, result in enumerate(results):
        if predicate(result):
            return index
    return None


def summarize_result(result: dict[str, Any], *, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "chunk_id": result.get("chunk_id"),
        "material_id": result.get("material_id"),
        "score": result.get("score"),
        "chunk_type": result.get("chunk_type"),
        "provider": result.get("provider"),
        "source_type": result.get("source_type"),
        "extraction_method": result.get("extraction_method"),
        "excerpt": result.get("excerpt"),
    }


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        f"status: {report['status']}",
        f"query: {report['query']}",
        f"mode: {report['mode']}",
        "checks:",
    ]
    for check in report["checks"]:
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- {mark} {check['name']} ({check['detail']})")
    lines.append("top_results:")
    for index, result in enumerate(report["top_results"], start=1):
        lines.append(
            f"- {index}. {result['chunk_id']} material={result['material_id']} "
            f"score={result['score']} type={result['chunk_type']} "
            f"provider={result['provider']} source_type={result['source_type']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = evaluate_search_quality(query=args.query, mode=args.mode, limit=args.limit)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text_report(report))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
