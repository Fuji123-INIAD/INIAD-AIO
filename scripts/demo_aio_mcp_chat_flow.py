"""Print a presentation-friendly AIO MCP demo flow."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.parse import urljoin

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_QUERY = "セキュリティ"


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
    parser.add_argument("--show-source-type", action="store_true")
    parser.add_argument("--show-provider", action="store_true")
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
    show_source_type: bool = False,
    show_provider: bool = False,
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

    first_item = first_context_item(context)
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


def context_is_metadata_only(context: dict[str, Any]) -> bool:
    items = context.get("items")
    if not isinstance(items, list) or not items:
        return False
    return all(
        isinstance(item, dict) and item.get("chunk_type") == "metadata"
        for item in items
    )


def render_markdown(
    backlog: dict[str, Any],
    context: dict[str, Any],
    material: dict[str, Any] | None,
    *,
    query: str,
    show_source_type: bool = False,
    show_provider: bool = False,
) -> str:
    lines = [
        "# AIO MCP Demo Flow",
        "",
        "## 1. Task backlog",
        "",
        str(backlog.get("summary") or "(summary unavailable)"),
        "",
    ]
    for item in backlog.get("items") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('display_course_name') or item.get('course_code')}: "
            f"{item.get('title')} / status={item.get('status')} / "
            f"deadline={item.get('deadline_text')}"
        )
    lines.extend(
        [
            "",
            f"## 2. Material search: {query}",
            "",
            str(context.get("summary") or "(summary unavailable)"),
            "",
        ]
    )
    for item in context.get("items") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('source_label')} "
            f"{source_badge(item, show_source_type=show_source_type, show_provider=show_provider)}"
            f"{metadata_note(item)}: {item.get('excerpt')}"
        )
    lines.extend(["", "## 3. First material snippets", ""])
    if material:
        chunks = material.get("chunks") or []
        if not chunks:
            lines.append("本文snippetはありません。PDF open URLまたはmetadataを確認してください。")
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            lines.append(
                f"- {chunk.get('source_label')} "
                f"{source_badge(chunk, show_source_type=show_source_type, show_provider=show_provider)}"
                f"{metadata_note(chunk)}: {chunk.get('text')}"
            )
    else:
        lines.append("本文snippetを取得できませんでした。metadata-only fallbackの可能性があります。")
    lines.extend(
        [
            "",
            "## 4. Caution",
            "",
            f"- Tasks: {backlog.get('caution')}",
            f"- Materials: {context.get('caution')}",
        ]
    )
    return "\n".join(lines)


def source_badge(
    item: dict[str, Any],
    *,
    show_source_type: bool,
    show_provider: bool,
) -> str:
    labels = []
    if show_source_type and item.get("source_type"):
        labels.append(str(item.get("source_type")))
    if show_provider and item.get("provider"):
        labels.append(str(item.get("provider")))
    return f"[{'/'.join(labels)}] " if labels else ""


def metadata_note(item: dict[str, Any]) -> str:
    if item.get("chunk_type") == "metadata" or item.get("text_available") is False:
        return "(metadata-only: 本文は未抽出)"
    return ""


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
