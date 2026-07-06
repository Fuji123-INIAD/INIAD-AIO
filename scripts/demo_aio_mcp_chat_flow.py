"""Print a presentation-friendly fallback flow for AIO MCP demos."""

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
        description="Run the task backlog -> material search -> snippet demo flow via FastAPI."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args(argv)


def run_demo(base_url: str, *, query: str, mode: str, limit: int) -> str:
    backlog = get_json(base_url, "/api/tasks/backlog/summary")
    context = get_json(
        base_url,
        "/api/context/search",
        params={"q": query, "mode": mode, "limit": limit},
    )
    first_item = first_context_item(context)
    material = None
    if first_item and first_item.get("material_id"):
        material = get_json(
            base_url,
            f"/api/materials/{first_item['material_id']}",
            params={"include_full_text": "false"},
        )
    return render_markdown(backlog, context, material, query=query)


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


def render_markdown(
    backlog: dict[str, Any],
    context: dict[str, Any],
    material: dict[str, Any] | None,
    *,
    query: str,
) -> str:
    lines = [
        "# AIO MCP Demo Flow",
        "",
        "## 1. 課題候補",
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
            "## 2. 講義資料検索: " + query,
            "",
            str(context.get("summary") or "(summary unavailable)"),
            "",
        ]
    )
    for item in context.get("items") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- {item.get('source_label')} [{item.get('source_type')}/{item.get('provider')}]: "
            f"{item.get('excerpt')}"
        )
    lines.extend(["", "## 3. 資料本文snippet", ""])
    if material:
        for chunk in material.get("chunks") or []:
            if not isinstance(chunk, dict):
                continue
            lines.append(f"- {chunk.get('source_label')}: {chunk.get('text')}")
    else:
        lines.append("検索結果から詳細取得できる資料はありませんでした。metadata fallbackのみの可能性があります。")
    lines.extend(
        [
            "",
            "## 4. 注意",
            "",
            f"- 課題: {backlog.get('caution')}",
            f"- 資料: {context.get('caution')}",
            "",
            "## 5. できること / できないこと",
            "",
            "- できること: 課題候補、資料候補、本文またはmetadata snippetを同じ流れで確認できます。",
            "- できないこと: tool resultにない締切・提出方法・評価条件は確定できません。",
            "- 本文抽出の限界: PDF通常テキスト層ではなく、MOOCs-Collect slide textやmetadataの場合があります。",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        print(run_demo(args.base_url, query=args.query, mode=args.mode, limit=args.limit))
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
