"""Build Claude-friendly context packs from material search hits."""

from __future__ import annotations

from typing import Any


MATERIAL_SEARCH_CAUTION = (
    "検索対象にはMOOCs-Collect由来テキスト、MOOCs HTML本文、PDF metadata等が"
    "含まれます。PDF通常テキスト層から抽出された本文とは限りません。"
)


def build_context_pack(
    *,
    query: str,
    results: list[dict[str, Any]],
    mode: str,
    limit: int,
) -> dict[str, Any]:
    items = [context_item(result) for result in results[:limit]]
    summary = (
        f"'{query}' の関連資料snippetは{len(items)}件です。"
        if items
        else f"'{query}' に一致する資料snippetは見つかりませんでした。"
    )
    return {
        "status": "ok",
        "summary": summary,
        "query": query,
        "mode": mode,
        "items": items,
        "caution": MATERIAL_SEARCH_CAUTION,
    }


def context_item(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "material_id": result.get("material_id"),
        "chunk_id": result.get("chunk_id"),
        "source_label": result.get("source_label"),
        "course_code": result.get("course_code"),
        "course_title": result.get("course_title"),
        "lecture_key": result.get("lecture_key"),
        "lecture_title": result.get("lecture_title"),
        "title": result.get("title"),
        "source_type": result.get("source_type"),
        "provider": result.get("provider"),
        "extraction_method": result.get("extraction_method"),
        "chunk_type": result.get("chunk_type"),
        "excerpt": result.get("excerpt") or result.get("text"),
        "score": result.get("score"),
        "open_url": result.get("open_url"),
        "text_available": result.get("chunk_type") != "metadata",
        "warnings": result.get("warnings") or [],
    }
