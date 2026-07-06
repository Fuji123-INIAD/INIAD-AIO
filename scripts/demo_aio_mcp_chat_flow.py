"""Print a presentation-friendly AIO MCP demo flow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import urljoin

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_QUERY = "セキュリティ"
SEARCH_SNIPPET_CHARS = 260
MATERIAL_SNIPPET_CHARS = 220


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+")
WHITESPACE_RE = re.compile(r"\s+")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run task backlog -> material search -> snippet demo flow via FastAPI."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="keyword")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--course-code")
    parser.add_argument("--course-title")
    parser.add_argument("--lecture-key")
    parser.add_argument("--lecture-title")
    parser.add_argument("--prefer-keyword-when-metadata-only", action="store_true")
    parser.add_argument("--show-source-type", action="store_true", default=True)
    parser.add_argument("--show-provider", action="store_true", default=True)
    return parser.parse_args(argv)


def run_demo(
    base_url: str,
    *,
    query: str,
    mode: str,
    limit: int,
    course_code: str | None = None,
    course_title: str | None = None,
    lecture_key: str | None = None,
    lecture_title: str | None = None,
    prefer_keyword_when_metadata_only: bool = False,
    show_source_type: bool = True,
    show_provider: bool = True,
) -> str:
    backlog = get_json(base_url, "/api/tasks/backlog/summary")
    params = compact_params(
        {
            "q": query,
            "mode": mode,
            "limit": limit,
            "course_code": course_code,
            "course_title": course_title,
            "lecture_key": lecture_key,
            "lecture_title": lecture_title,
        }
    )
    context = get_json(base_url, "/api/context/search", params=params)
    if (
        prefer_keyword_when_metadata_only
        and mode == "hybrid"
        and context_is_metadata_only(context)
    ):
        params["mode"] = "keyword"
        context = get_json(base_url, "/api/context/search", params=params)

    first_item = first_material_context_item(context)
    material = None
    if first_item and first_item.get("material_id"):
        material = get_json(
            base_url,
            f"/api/materials/{first_item['material_id']}",
            params={"include_full_text": "false"},
        )
    return render_markdown(
        backlog,
        context,
        material,
        query=query,
        show_source_type=show_source_type,
        show_provider=show_provider,
    )


def get_json(base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object JSON from {url}")
    return payload


def first_context_item(context: dict[str, Any]) -> dict[str, Any] | None:
    items = context.get("items")
    if not isinstance(items, list) or not items:
        return None
    return items[0] if isinstance(items[0], dict) else None


def first_material_context_item(context: dict[str, Any]) -> dict[str, Any] | None:
    text_items, _metadata_items = split_items(context.get("items"))
    if text_items:
        return text_items[0]
    return first_context_item(context)


def context_is_metadata_only(context: dict[str, Any]) -> bool:
    items = context.get("items")
    if not isinstance(items, list) or not items:
        return False
    return all(is_metadata_only(item) for item in items if isinstance(item, dict))


def render_markdown(
    backlog: dict[str, Any],
    context: dict[str, Any],
    material: dict[str, Any] | None,
    *,
    query: str,
    show_source_type: bool = True,
    show_provider: bool = True,
) -> str:
    lines = [
        "# AIO MCP Demo Flow",
        "",
        "## 1. Task backlog",
        "",
        clean_snippet(backlog.get("summary") or "(summary unavailable)", 320),
        "",
    ]
    for item in backlog.get("items") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {clean_inline(item.get('display_course_name') or item.get('course_code'))}: "
            f"{clean_inline(item.get('title'))} / status={clean_inline(item.get('status'))} / "
            f"deadline={clean_inline(item.get('deadline_text'))}"
        )

    text_items, metadata_items = split_items(context.get("items"))
    lines.extend(
        [
            "",
            f"## 2. Material search: {query}",
            "",
            clean_snippet(context.get("summary") or "(summary unavailable)", 320),
            "",
            "### Text snippets / 本文あり候補",
            "",
        ]
    )
    if text_items:
        for item in text_items:
            lines.extend(render_result_item(item, show_source_type, show_provider))
    else:
        lines.append("- 本文ありsnippetは見つかりませんでした。metadata-only fallback を確認してください。")

    lines.extend(["", "### Metadata-only fallback", ""])
    if metadata_items:
        for item in metadata_items:
            lines.extend(render_result_item(item, show_source_type, show_provider))
    else:
        lines.append("- metadata-only fallback はありません。")

    lines.extend(["", "## 3. First material snippets", ""])
    if material:
        text_chunks, metadata_chunks = split_items(material.get("chunks"))
        if text_chunks:
            for chunk in text_chunks[:3]:
                lines.extend(
                    render_result_item(
                        chunk,
                        show_source_type,
                        show_provider,
                        text_key="text",
                        max_chars=MATERIAL_SNIPPET_CHARS,
                    )
                )
        elif metadata_chunks:
            lines.append("- 本文ありchunkはありません。metadata-only fallback です。")
            for chunk in metadata_chunks[:3]:
                lines.extend(
                    render_result_item(
                        chunk,
                        show_source_type,
                        show_provider,
                        text_key="text",
                        max_chars=MATERIAL_SNIPPET_CHARS,
                    )
                )
        else:
            lines.append("- 本文snippetはありません。PDF open URL またはmetadataを確認してください。")
    else:
        lines.append("- 本文snippetを取得できませんでした。metadata-only fallback の可能性があります。")

    lines.extend(
        [
            "",
            "## 4. Caution",
            "",
            f"- Tasks: {clean_snippet(backlog.get('caution') or '(none)', 260)}",
            "- Materials: 本文snippetは MOOCs-Collect search_index 由来の場合があり、PDF通常テキスト層からの抽出とは限りません。",
            "- Materials: 講義資料全文を完全に読める、または回答が必ず正確になる、とは言い切りません。",
            f"- API caution: {clean_snippet(context.get('caution') or '(none)', 260)}",
        ]
    )
    return "\n".join(lines)


def render_result_item(
    item: dict[str, Any],
    show_source_type: bool,
    show_provider: bool,
    *,
    text_key: str = "excerpt",
    max_chars: int = SEARCH_SNIPPET_CHARS,
) -> list[str]:
    label = clean_inline(item.get("source_label") or item.get("title") or item.get("material_id"))
    detail = source_badge(
        item,
        show_source_type=show_source_type,
        show_provider=show_provider,
    )
    score = item.get("score")
    score_label = f" / score={score}" if score is not None else ""
    note = " / metadata-only: 本文未抽出" if is_metadata_only(item) else ""
    open_url = item.get("open_url")
    open_label = f" / open={clean_inline(open_url)}" if open_url and is_metadata_only(item) else ""
    snippet = clean_snippet(item.get(text_key) or item.get("excerpt") or item.get("text"), max_chars)
    if not snippet:
        snippet = "(snippet unavailable)"
    return [
        f"- {label} [{detail}{score_label}{note}{open_label}]",
        f"  {snippet}",
    ]


def split_items(items: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text_items: list[dict[str, Any]] = []
    metadata_items: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return text_items, metadata_items
    for item in items:
        if not isinstance(item, dict):
            continue
        if is_metadata_only(item):
            metadata_items.append(item)
        else:
            text_items.append(item)
    return text_items, metadata_items


def source_badge(
    item: dict[str, Any],
    *,
    show_source_type: bool,
    show_provider: bool,
) -> str:
    labels = []
    labels.append("metadata-only" if is_metadata_only(item) else "text")
    if show_provider:
        labels.append(f"provider={clean_inline(item.get('provider') or 'unknown')}")
    if show_source_type:
        labels.append(f"source_type={clean_inline(item.get('source_type') or 'unknown')}")
    if item.get("extraction_method"):
        labels.append(f"method={clean_inline(item.get('extraction_method'))}")
    return " / ".join(labels)


def is_metadata_only(item: dict[str, Any]) -> bool:
    return (
        item.get("chunk_type") == "metadata"
        or item.get("text_available") is False
        or item.get("extraction_method") == "metadata_only"
    )


def clean_inline(value: Any) -> str:
    return clean_snippet(value, 120)


def clean_snippet(value: Any, max_chars: int) -> str:
    text = CONTROL_CHARS_RE.sub(" ", str(value or ""))
    text = WHITESPACE_RE.sub(" ", text).strip()
    limit = max(20, int(max_chars))
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def compact_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if value is not None and str(value).strip() != ""
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        print(
            run_demo(
                args.base_url,
                query=args.query,
                mode=args.mode,
                limit=args.limit,
                course_code=args.course_code,
                course_title=args.course_title,
                lecture_key=args.lecture_key,
                lecture_title=args.lecture_title,
                prefer_keyword_when_metadata_only=args.prefer_keyword_when_metadata_only,
                show_source_type=args.show_source_type,
                show_provider=args.show_provider,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "detail": str(exc), "base_url": args.base_url},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
