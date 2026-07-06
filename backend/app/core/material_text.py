"""Common material text model for PDF, MOOCs, slide, and OCR providers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


SOURCE_TYPE_PDF_NATIVE = "pdf_native"
SOURCE_TYPE_PDF_METADATA = "pdf_metadata"
SOURCE_TYPE_MOOCS_COLLECT_SLIDE_TEXT = "moocs_collect_slide_text"
SOURCE_TYPE_MOOCS_COLLECT_SEARCH_INDEX = "moocs_collect_search_index"
SOURCE_TYPE_MOOCS_COLLECT_APPDATA_FILE = "moocs_collect_appdata_file"
SOURCE_TYPE_MOOCS_COLLECT_SLIDE_URL_DOM = "moocs_collect_slide_url_dom"
SOURCE_TYPE_MOOCS_COLLECT_PDF_NATIVE = "moocs_collect_pdf_native"
SOURCE_TYPE_MOOCS_COLLECT_PDF_OCR = "moocs_collect_pdf_ocr"
SOURCE_TYPE_MOOCS_HTML = "moocs_html"
SOURCE_TYPE_OCR = "ocr"
SOURCE_TYPE_UNKNOWN = "unknown"

EXTRACTION_METHOD_PYPDF = "pypdf"
EXTRACTION_METHOD_PYMUPDF = "pymupdf"
EXTRACTION_METHOD_METADATA_ONLY = "metadata_only"
EXTRACTION_METHOD_MOOCS_COLLECT_SVG_TEXT = "moocs_collect_svg_text"
EXTRACTION_METHOD_SEARCH_INDEX = "search_index"
EXTRACTION_METHOD_APPDATA_HTML = "appdata_html"
EXTRACTION_METHOD_APPDATA_SVG = "appdata_svg"
EXTRACTION_METHOD_APPDATA_JSON = "appdata_json"
EXTRACTION_METHOD_APPDATA_TEXT = "appdata_text"
EXTRACTION_METHOD_SLIDE_URL_DOM = "slide_url_dom"
EXTRACTION_METHOD_SLIDE_URL_SVG = "slide_url_svg"
EXTRACTION_METHOD_SLIDE_URL_ARIA_LABEL = "slide_url_aria_label"
EXTRACTION_METHOD_MOOCS_HTML_PARSER = "moocs_html_parser"
EXTRACTION_METHOD_OCR_MYPDF = "ocrmypdf"
EXTRACTION_METHOD_PADDLEOCR = "paddleocr"
EXTRACTION_METHOD_DOCLING = "docling"
EXTRACTION_METHOD_MARKER = "marker"
EXTRACTION_METHOD_UNKNOWN = "unknown"


@dataclass(frozen=True)
class MaterialText:
    material_id: str
    course_code: str | None
    course_title: str | None
    lecture_key: str | None
    lecture_title: str | None
    title: str
    source_type: str
    source_ref: str | None
    source_url: str | None
    local_resource_id: str | None
    text_available: bool
    extraction_method: str
    provider: str
    text: str
    text_length: int
    language: str
    warnings: list[dict[str, str]] = field(default_factory=list)
    indexed_at: str | None = None

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_text:
            data.pop("text", None)
        return data


def material_from_dict(data: dict[str, Any]) -> MaterialText:
    text = str(data.get("text") or "")
    return MaterialText(
        material_id=str(data.get("material_id") or stable_material_id(data)),
        course_code=nullable_text(data.get("course_code")),
        course_title=nullable_text(data.get("course_title")),
        lecture_key=nullable_text(data.get("lecture_key")),
        lecture_title=nullable_text(data.get("lecture_title")),
        title=str(data.get("title") or "Untitled material"),
        source_type=str(data.get("source_type") or SOURCE_TYPE_UNKNOWN),
        source_ref=nullable_text(data.get("source_ref")),
        source_url=nullable_text(data.get("source_url")),
        local_resource_id=nullable_text(data.get("local_resource_id")),
        text_available=bool(data.get("text_available")) and bool(text.strip()),
        extraction_method=str(data.get("extraction_method") or EXTRACTION_METHOD_UNKNOWN),
        provider=str(data.get("provider") or "unknown"),
        text=text,
        text_length=int(data.get("text_length") or len(text)),
        language=str(data.get("language") or "ja"),
        warnings=list(data.get("warnings") or []),
        indexed_at=nullable_text(data.get("indexed_at")),
    )


def material_texts_from_local_resources(
    resources: list[dict[str, Any]],
    *,
    index_path: Path | None = None,
    include_text_cache: bool = True,
    base_url: str | None = None,
) -> list[MaterialText]:
    materials: list[MaterialText] = []
    for resource in resources:
        pages = (
            load_text_cache_pages(resource, index_path)
            if include_text_cache
            else []
        )
        materials.append(
            material_text_from_local_resource(
                resource,
                pages=pages,
                base_url=base_url,
            )
        )
    return materials


def material_text_from_local_resource(
    resource: dict[str, Any],
    *,
    pages: list[dict[str, Any]] | None = None,
    base_url: str | None = None,
) -> MaterialText:
    pages = pages or []
    text = "\n\n".join(
        f"Page {page.get('page_number')}: {str(page.get('text') or '').strip()}"
        for page in pages
        if str(page.get("text") or "").strip()
    ).strip()
    metadata_text = local_resource_metadata_text(resource)
    text_available = bool(text)
    source_type = SOURCE_TYPE_PDF_NATIVE if text_available else SOURCE_TYPE_PDF_METADATA
    extraction_method = (
        infer_text_cache_extractor(resource, pages)
        if text_available
        else EXTRACTION_METHOD_METADATA_ONLY
    )
    material_id = stable_material_id(
        "local-resource",
        resource.get("resource_id"),
        resource.get("title"),
    )
    source_url = absolute_or_relative_url(
        local_resource_open_url(str(resource.get("resource_id") or "")),
        base_url,
    )
    warnings = list(resource.get("warnings") or [])
    if not text_available:
        warnings.append(
            {
                "message": (
                    "PDF本文テキストは利用できないため、metadata-only materialとして"
                    "講義回・タイトル・Context Cardを検索対象にします。"
                )
            }
        )
    body = text if text_available else metadata_text
    return MaterialText(
        material_id=material_id,
        course_code=nullable_text(resource.get("course_code")),
        course_title=nullable_text(resource.get("course_title")),
        lecture_key=nullable_text(resource.get("lecture_key")),
        lecture_title=nullable_text(resource.get("lecture_title")),
        title=str(resource.get("title") or "Untitled PDF"),
        source_type=source_type,
        source_ref=nullable_text(resource.get("local_path")),
        source_url=source_url,
        local_resource_id=nullable_text(resource.get("resource_id")),
        text_available=text_available,
        extraction_method=extraction_method,
        provider="local_resource_index",
        text=body,
        text_length=len(body),
        language="ja",
        warnings=warnings,
        indexed_at=utc_now_iso(),
    )


def local_resource_metadata_text(resource: dict[str, Any]) -> str:
    values = [
        resource.get("course_code"),
        resource.get("course_title"),
        resource.get("lecture_key"),
        resource.get("lecture_title"),
        resource.get("title"),
        resource.get("card_text"),
    ]
    warning_text = " ".join(
        str(warning.get("message") or "")
        for warning in resource.get("warnings") or []
        if isinstance(warning, dict)
    )
    values.append(warning_text)
    return " / ".join(str(value).strip() for value in values if str(value or "").strip())


def load_text_cache_pages(
    resource: dict[str, Any],
    index_path: Path | None,
) -> list[dict[str, Any]]:
    cache_path = resolve_text_cache_path(resource.get("text_cache_path"), index_path)
    if cache_path is None or not cache_path.exists():
        return []
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return []
    normalized = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        text = str(page.get("text") or "").strip()
        if not text:
            continue
        normalized.append({"page_number": page.get("page_number"), "text": text})
    return normalized


def resolve_text_cache_path(text_cache_path: Any, index_path: Path | None) -> Path | None:
    if not text_cache_path:
        return None
    candidate = Path(str(text_cache_path)).expanduser()
    if candidate.is_absolute():
        return candidate
    if index_path is not None:
        return index_path.expanduser().resolve().parent / candidate
    return Path.cwd() / candidate


def infer_text_cache_extractor(
    resource: dict[str, Any],
    pages: list[dict[str, Any]],
) -> str:
    cache_path = str(resource.get("text_cache_path") or "")
    lowered = cache_path.lower()
    if "pymupdf" in lowered:
        return EXTRACTION_METHOD_PYMUPDF
    if "pypdf" in lowered:
        return EXTRACTION_METHOD_PYPDF
    return EXTRACTION_METHOD_UNKNOWN if not pages else EXTRACTION_METHOD_PYPDF


def local_resource_open_url(resource_id: str) -> str | None:
    if not resource_id:
        return None
    return f"/api/local/resources/{quote(resource_id, safe='')}/file"


def absolute_or_relative_url(url: str | None, base_url: str | None) -> str | None:
    if not url or not base_url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return base_url.rstrip("/") + "/" + url.lstrip("/")


def stable_material_id(*parts: Any) -> str:
    if len(parts) == 1 and isinstance(parts[0], dict):
        values = [
            parts[0].get("source_type"),
            parts[0].get("source_ref"),
            parts[0].get("local_resource_id"),
            parts[0].get("title"),
        ]
    else:
        values = list(parts)
    raw = "|".join(str(value or "") for value in values)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"material:{digest}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
