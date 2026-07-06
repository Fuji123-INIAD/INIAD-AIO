"""Chunk MaterialText records into searchable, source-preserving snippets."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.core.material_text import (
    MaterialText,
    SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT,
    SOURCE_TYPE_MOOCS_HTML,
    SOURCE_TYPE_OCR,
    SOURCE_TYPE_PDF_METADATA,
    SOURCE_TYPE_PDF_NATIVE,
)


CHUNK_TYPE_SLIDE = "slide"
CHUNK_TYPE_HTML_SECTION = "html_section"
CHUNK_TYPE_PDF_PAGE = "pdf_page"
CHUNK_TYPE_METADATA = "metadata"
CHUNK_TYPE_OCR_PAGE = "ocr_page"
CHUNK_TYPE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class MaterialChunk:
    chunk_id: str
    material_id: str
    course_code: str | None
    course_title: str | None
    lecture_key: str | None
    lecture_title: str | None
    title: str
    chunk_index: int
    chunk_type: str
    text: str
    text_length: int
    source_label: str
    open_url: str | None
    source_type: str
    provider: str
    extraction_method: str
    local_resource_id: str | None
    ontology_tags: list[str] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chunk_from_dict(data: dict[str, Any]) -> MaterialChunk:
    text = str(data.get("text") or "")
    return MaterialChunk(
        chunk_id=str(data.get("chunk_id") or stable_chunk_id(data.get("material_id"), 0, text)),
        material_id=str(data.get("material_id") or ""),
        course_code=nullable_text(data.get("course_code")),
        course_title=nullable_text(data.get("course_title")),
        lecture_key=nullable_text(data.get("lecture_key")),
        lecture_title=nullable_text(data.get("lecture_title")),
        title=str(data.get("title") or "Untitled material"),
        chunk_index=int(data.get("chunk_index") or 0),
        chunk_type=str(data.get("chunk_type") or CHUNK_TYPE_UNKNOWN),
        text=text,
        text_length=int(data.get("text_length") or len(text)),
        source_label=str(data.get("source_label") or ""),
        open_url=nullable_text(data.get("open_url")),
        source_type=str(data.get("source_type") or ""),
        provider=str(data.get("provider") or "unknown"),
        extraction_method=str(data.get("extraction_method") or "unknown"),
        local_resource_id=nullable_text(data.get("local_resource_id")),
        ontology_tags=[str(tag) for tag in data.get("ontology_tags") or []],
        warnings=list(data.get("warnings") or []),
    )


def chunk_material_text(
    material: MaterialText,
    *,
    max_chars: int = 1200,
) -> list[MaterialChunk]:
    text = str(material.text or "").strip()
    if not text:
        text = metadata_fallback_text(material)
    chunk_type = infer_chunk_type(material)
    if material.source_type == SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT:
        pieces = split_slide_blocks(text, max_chars=max_chars)
    elif material.source_type in {SOURCE_TYPE_PDF_NATIVE, SOURCE_TYPE_OCR}:
        pieces = split_page_blocks(text, max_chars=max_chars)
    else:
        pieces = split_text(text, max_chars=max_chars)
    if not pieces:
        pieces = [metadata_fallback_text(material)]
        chunk_type = CHUNK_TYPE_METADATA

    chunks = []
    for index, piece in enumerate(pieces):
        normalized_piece = normalize_chunk_text(piece)
        if not normalized_piece:
            continue
        current_type = chunk_type
        if not material.text_available or material.source_type == SOURCE_TYPE_PDF_METADATA:
            current_type = CHUNK_TYPE_METADATA
        chunks.append(
            MaterialChunk(
                chunk_id=stable_chunk_id(material.material_id, index, normalized_piece),
                material_id=material.material_id,
                course_code=material.course_code,
                course_title=material.course_title,
                lecture_key=material.lecture_key,
                lecture_title=material.lecture_title,
                title=material.title,
                chunk_index=index,
                chunk_type=current_type,
                text=normalized_piece,
                text_length=len(normalized_piece),
                source_label=source_label(material),
                open_url=material.source_url,
                source_type=material.source_type,
                provider=material.provider,
                extraction_method=material.extraction_method,
                local_resource_id=material.local_resource_id,
                ontology_tags=ontology_tags(material, current_type),
                warnings=material.warnings,
            )
        )
    return chunks


def chunk_material_texts(materials: list[MaterialText], *, max_chars: int = 1200) -> list[MaterialChunk]:
    chunks: list[MaterialChunk] = []
    for material in materials:
        chunks.extend(chunk_material_text(material, max_chars=max_chars))
    return chunks


def infer_chunk_type(material: MaterialText) -> str:
    if material.source_type == SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT:
        return CHUNK_TYPE_SLIDE
    if material.source_type == SOURCE_TYPE_MOOCS_HTML:
        return CHUNK_TYPE_HTML_SECTION
    if material.source_type == SOURCE_TYPE_PDF_NATIVE:
        return CHUNK_TYPE_PDF_PAGE
    if material.source_type == SOURCE_TYPE_PDF_METADATA:
        return CHUNK_TYPE_METADATA
    if material.source_type == SOURCE_TYPE_OCR:
        return CHUNK_TYPE_OCR_PAGE
    return CHUNK_TYPE_UNKNOWN


def split_slide_blocks(text: str, *, max_chars: int) -> list[str]:
    blocks = re.split(r"(?=^Slide\s+\d+\s*:)", text, flags=re.MULTILINE)
    blocks = [block.strip() for block in blocks if block.strip()]
    return blocks if len(blocks) > 1 else split_text(text, max_chars=max_chars)


def split_page_blocks(text: str, *, max_chars: int) -> list[str]:
    blocks = re.split(r"(?=^Page\s+\d+\s*:)", text, flags=re.MULTILINE)
    blocks = [block.strip() for block in blocks if block.strip()]
    return blocks if len(blocks) > 1 else split_text(text, max_chars=max_chars)


def split_text(text: str, *, max_chars: int) -> list[str]:
    normalized = normalize_chunk_text(text)
    if not normalized:
        return []
    if len(normalized) <= max_chars:
        return [normalized]
    pieces = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            break_at = normalized.rfind("。", start, end)
            if break_at > start + max_chars // 2:
                end = break_at + 1
        pieces.append(normalized[start:end].strip())
        start = end
    return [piece for piece in pieces if piece]


def metadata_fallback_text(material: MaterialText) -> str:
    return " / ".join(
        value
        for value in (
            material.course_code,
            material.course_title,
            material.lecture_key,
            material.lecture_title,
            material.title,
        )
        if value
    )


def source_label(material: MaterialText) -> str:
    parts = []
    if material.course_title or material.course_code:
        parts.append(material.course_title or material.course_code or "")
    if material.lecture_key:
        lecture = f"第{material.lecture_key}回"
        if material.lecture_title:
            lecture += f" {material.lecture_title}"
        parts.append(lecture)
    elif material.lecture_title:
        parts.append(material.lecture_title)
    parts.append(material.title)
    return " / ".join(part for part in parts if part)


def ontology_tags(material: MaterialText, chunk_type: str) -> list[str]:
    tags = ["material", chunk_type, material.source_type, material.provider]
    for value in (material.course_code, material.lecture_key):
        if value:
            tags.append(str(value))
    return sorted(set(tags))


def normalize_chunk_text(value: str) -> str:
    return " ".join(str(value or "").split())


def stable_chunk_id(material_id: Any, chunk_index: int, text: str) -> str:
    raw = f"{material_id}|{chunk_index}|{text}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"material-chunk:{digest}"


def nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
