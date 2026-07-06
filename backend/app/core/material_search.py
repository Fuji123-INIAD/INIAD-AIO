"""Keyword, semantic, and hybrid search over MaterialChunk indexes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.core.context_pack import build_context_pack
from backend.app.core.embeddings import (
    HashedBagOfWordsEmbeddingProvider,
    cosine_similarity,
)
from backend.app.core.material_chunks import MaterialChunk, chunk_from_dict
from backend.app.core.material_text import MaterialText, material_from_dict


SEARCH_MODES = frozenset({"keyword", "semantic", "hybrid"})
DEFAULT_EMBEDDING_PROVIDER = HashedBagOfWordsEmbeddingProvider()


def load_material_text_index(index_path: Path) -> tuple[list[MaterialText], list[dict[str, str]]]:
    resolved = index_path.expanduser()
    if not resolved.exists():
        return [], [{"message": f"Material text index has not been generated yet: {resolved}"}]
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [{"message": f"Could not read material text index: {exc}"}]
    rows = payload.get("materials") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return [], [{"message": "Material text index materials must be an array."}]
    return [material_from_dict(row) for row in rows if isinstance(row, dict)], list(payload.get("warnings", []) if isinstance(payload, dict) else [])


def load_material_chunk_index(index_path: Path) -> tuple[list[MaterialChunk], list[dict[str, str]]]:
    resolved = index_path.expanduser()
    if not resolved.exists():
        return [], [{"message": f"Material chunk index has not been generated yet: {resolved}"}]
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [{"message": f"Could not read material chunk index: {exc}"}]
    rows = payload.get("chunks") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return [], [{"message": "Material chunk index chunks must be an array."}]
    return [chunk_from_dict(row) for row in rows if isinstance(row, dict)], list(payload.get("warnings", []) if isinstance(payload, dict) else [])


def search_material_chunks(
    chunks: list[MaterialChunk],
    *,
    query: str,
    mode: str = "keyword",
    limit: int = 10,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized_mode = normalize_mode(mode)
    if normalized_mode is None:
        raise ValueError("mode must be one of: keyword, semantic, hybrid")
    filtered = [chunk for chunk in chunks if chunk_matches_filters(chunk, filters or {})]
    if normalized_mode == "semantic":
        results = semantic_results(filtered, query)
    elif normalized_mode == "hybrid":
        results = hybrid_results(filtered, query)
    else:
        results = keyword_results(filtered, query)
    results.sort(
        key=lambda result: (
            -float(result.get("score") or 0),
            1 if result.get("chunk_type") == "metadata" else 0,
            result.get("source_label") or "",
        )
    )
    return results[: max(1, min(limit, 50))]


def search_context_pack(
    chunks: list[MaterialChunk],
    *,
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results = search_material_chunks(
        chunks,
        query=query,
        mode=mode,
        limit=limit,
        filters=filters,
    )
    return build_context_pack(query=query, results=results, mode=normalize_mode(mode) or mode, limit=limit)


def keyword_results(chunks: list[MaterialChunk], query: str) -> list[dict[str, Any]]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return []
    results = []
    terms = [term for term in normalized_query.split() if term]
    for chunk in chunks:
        haystack = normalize_text(search_document(chunk))
        full_match = normalized_query in haystack
        term_hits = sum(1 for term in terms if term in haystack)
        if not full_match and term_hits == 0:
            continue
        score = 2.0 if full_match else 0.0
        score += term_hits
        if chunk.chunk_type != "metadata":
            score += 0.25
        results.append(result_from_chunk(chunk, query=query, score=score, search_mode="keyword"))
    return results


def semantic_results(chunks: list[MaterialChunk], query: str) -> list[dict[str, Any]]:
    query_vector = DEFAULT_EMBEDDING_PROVIDER.embed(query)
    results = []
    for chunk in chunks:
        score = cosine_similarity(query_vector, DEFAULT_EMBEDDING_PROVIDER.embed(search_document(chunk)))
        if score <= 0:
            continue
        results.append(result_from_chunk(chunk, query=query, score=round(score, 4), search_mode="semantic"))
    return results


def hybrid_results(chunks: list[MaterialChunk], query: str) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for result in keyword_results(chunks, query):
        merged[result["chunk_id"]] = {**result, "search_mode": "hybrid", "score": result["score"] + 2.0}
    for result in semantic_results(chunks, query):
        existing = merged.get(result["chunk_id"])
        if existing is not None:
            existing["score"] = round(float(existing["score"]) + float(result["score"]), 4)
            continue
        merged[result["chunk_id"]] = {**result, "search_mode": "hybrid"}
    return list(merged.values())


def result_from_chunk(
    chunk: MaterialChunk,
    *,
    query: str,
    score: float,
    search_mode: str,
) -> dict[str, Any]:
    data = chunk.to_dict()
    data.update(
        {
            "excerpt": make_excerpt(chunk.text, query),
            "score": round(float(score), 4),
            "search_mode": search_mode,
        }
    )
    return data


def chunk_matches_filters(chunk: MaterialChunk, filters: dict[str, Any]) -> bool:
    for key in (
        "course_code",
        "course_title",
        "lecture_key",
        "lecture_title",
        "source_type",
    ):
        expected = filters.get(key)
        if expected in (None, ""):
            continue
        actual = getattr(chunk, key)
        if normalize_text(expected) not in normalize_text(actual):
            return False
    resource_kind = filters.get("resource_kind")
    if resource_kind and normalize_text(resource_kind) not in normalize_text(chunk.ontology_tags):
        return False
    entity_type = filters.get("entity_type")
    if entity_type and normalize_text(entity_type) not in normalize_text(chunk.ontology_tags):
        return False
    return True


def search_document(chunk: MaterialChunk) -> str:
    return " ".join(
        str(value or "")
        for value in (
            chunk.text,
            chunk.source_label,
            chunk.course_code,
            chunk.course_title,
            chunk.lecture_key,
            chunk.lecture_title,
            chunk.title,
            chunk.source_type,
            chunk.provider,
            " ".join(chunk.ontology_tags),
        )
    )


def make_excerpt(text: str, query: str, *, radius: int = 90) -> str:
    collapsed = " ".join(str(text or "").split())
    if not collapsed:
        return ""
    normalized_query = normalize_text(query)
    normalized_text = normalize_text(collapsed)
    if not normalized_query:
        return collapsed[:220]
    position = normalized_text.find(normalized_query)
    if position < 0:
        return collapsed[:220]
    start = max(0, position - radius)
    end = min(len(collapsed), position + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(collapsed) else ""
    return f"{prefix}{collapsed[start:end]}{suffix}"


def normalize_mode(mode: str) -> str | None:
    normalized = str(mode or "keyword").strip().casefold()
    return normalized if normalized in SEARCH_MODES else None


def normalize_text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return (
        str(value or "")
        .casefold()
        .replace("　", " ")
        .replace("Ⅰ", "i")
        .replace("ⅰ", "i")
        .replace("１", "1")
    )
