"""Extract safe text from cached MOOCs HTML and convert it to MaterialText."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.app.core.material_text import (
    EXTRACTION_METHOD_MOOCS_HTML_PARSER,
    SOURCE_TYPE_MOOCS_HTML,
    MaterialText,
    stable_material_id,
    utc_now_iso,
)


def extract_text_from_html(html: str, *, limit: int = 8000) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return fallback_strip_html(html, limit=limit)

    soup = BeautifulSoup(html or "", "html.parser")
    for selector in (
        "script",
        "style",
        "noscript",
        "nav",
        "header",
        "footer",
        "aside",
        "iframe",
        "form",
        ".navbar",
        ".sidebar",
        ".breadcrumb",
        ".pagination",
    ):
        for element in soup.select(selector):
            element.decompose()
    candidates = []
    for selector in ("main", "article", "section.content", ".content-wrapper", "body"):
        for element in soup.select(selector):
            text = compact_text(element.get_text(separator=" ", strip=True))
            if text:
                candidates.append(text)
    text = max(candidates, key=len, default="")
    return text[:limit].rstrip()


def material_text_from_html(
    html: str,
    *,
    title: str,
    source_ref: str | None = None,
    source_url: str | None = None,
    course_code: str | None = None,
    course_title: str | None = None,
    lecture_key: str | None = None,
    lecture_title: str | None = None,
) -> MaterialText:
    text = extract_text_from_html(html)
    material_id = stable_material_id("moocs-html", source_ref, source_url, title)
    warnings = []
    if not text:
        warnings.append({"message": "MOOCs HTML本文を抽出できなかったため空のMaterialTextです。"})
    return MaterialText(
        material_id=material_id,
        course_code=course_code,
        course_title=course_title,
        lecture_key=lecture_key,
        lecture_title=lecture_title,
        title=title,
        source_type=SOURCE_TYPE_MOOCS_HTML,
        source_ref=source_ref,
        source_url=source_url,
        local_resource_id=None,
        text_available=bool(text),
        extraction_method=EXTRACTION_METHOD_MOOCS_HTML_PARSER,
        provider="moocs_html_cache",
        text=text,
        text_length=len(text),
        language="ja",
        warnings=warnings,
        indexed_at=utc_now_iso(),
    )


def load_html_cache_materials(cache_dir: Path) -> tuple[list[MaterialText], list[dict[str, str]]]:
    resolved = cache_dir.expanduser()
    if not resolved.exists():
        return [], [{"message": f"MOOCs HTML cache directory not found: {resolved}"}]
    materials = []
    warnings = []
    for path in sorted(resolved.rglob("*.html")):
        try:
            html = path.read_text(encoding="utf-8")
        except Exception as exc:
            warnings.append({"message": f"Could not read HTML cache {path.name}: {exc}"})
            continue
        materials.append(
            material_text_from_html(
                html,
                title=path.stem,
                source_ref=str(path),
            )
        )
    return materials, warnings


def fallback_strip_html(html: str, *, limit: int) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return compact_text(text)[:limit].rstrip()


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())
