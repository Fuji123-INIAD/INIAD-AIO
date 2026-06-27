"""Probe Google Slides SVG aria-label text through a Playwright profile."""

from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_moocs_collect_page_join import (
    load_aio_page_keys,
    open_readonly_database,
)
from scripts.probe_moocs_collect_pdf_text import (
    extract_deadline_candidates,
    extract_keyword_contexts,
    filter_keys,
)
from scripts.probe_moocs_collect_slide_svg_text import fetch_slide_url_rows


SIGNIN_MARKERS = ("accounts.google.com", "signin", "login", "chooseaccount")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open MOOCs-Collect Google Slides URLs through a Playwright persistent "
            "profile and print bounded SVG aria-label snippets only."
        )
    )
    parser.add_argument("probe_json", type=Path, help="Path to AIO probe JSON")
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite")
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        required=True,
        help="Playwright Chromium persistent profile directory.",
    )
    parser.add_argument(
        "--course-code",
        action="append",
        default=[],
        help="Restrict to a course code segment such as COT105. Can be passed multiple times.",
    )
    parser.add_argument(
        "--page-key",
        action="append",
        default=[],
        help="Restrict to an exact pages.key value. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Maximum number of slide URLs to open.",
    )
    parser.add_argument(
        "--max-snippets",
        type=int,
        default=20,
        help="Maximum keyword snippets across the whole output.",
    )
    parser.add_argument(
        "--snippets-per-slide",
        type=int,
        default=3,
        help="Maximum keyword snippets per slide URL.",
    )
    parser.add_argument(
        "--snippet-chars",
        type=int,
        default=300,
        help="Maximum characters per keyword context snippet.",
    )
    parser.add_argument(
        "--goto-timeout-ms",
        type=int,
        default=30000,
        help="page.goto timeout in milliseconds.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=5000,
        help="Extra wait after page.goto so Google Slides can render SVG DOM.",
    )
    parser.add_argument(
        "--manual-login-wait-ms",
        type=int,
        default=0,
        help="Optional extra wait if a signin/login redirect is detected.",
    )
    return parser.parse_args()


def playwright_runner():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed in this Python environment. "
            "Activate .venv or run `pip install -r backend/requirements.txt`, "
            "then `playwright install chromium` if browsers are missing."
        ) from exc
    return sync_playwright()


def is_signin_redirect(url: str, title: str = "") -> bool:
    haystack = f"{url} {title}".lower()
    return any(marker in haystack for marker in SIGNIN_MARKERS)


def dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = re.sub(r"\s+", " ", value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def collect_svg_aria_labels_from_page(page: Any) -> dict[str, Any]:
    labels: list[str] = []
    svg_count = 0
    frame_count = 0
    frame_errors = 0
    for frame in page.frames:
        frame_count += 1
        try:
            svg_count += int(frame.locator("svg").count())
            frame_labels = frame.eval_on_selector_all(
                'svg g[role="img"][aria-label]',
                "(elements) => elements.map((element) => element.getAttribute('aria-label') || '')",
            )
            labels.extend(str(label) for label in frame_labels)
        except Exception:
            frame_errors += 1
    return {
        "svg_count": svg_count,
        "aria_labels": dedupe_texts(labels),
        "frame_count": frame_count,
        "frame_errors": frame_errors,
    }


def build_slide_result(
    row: dict[str, Any],
    page_loaded: bool,
    final_url: str,
    title: str,
    svg_count: int,
    aria_labels: list[str],
    max_snippets: int,
    snippets_per_slide: int,
    snippet_chars: int,
    error: str | None = None,
) -> dict[str, Any]:
    slide_text = "\n".join(aria_labels)
    per_slide_limit = min(snippets_per_slide, max_snippets)
    keyword_contexts = extract_keyword_contexts(
        slide_text,
        max_snippets=per_slide_limit,
        snippet_chars=snippet_chars,
    )
    return {
        "slide_url": row["slide_url"],
        "page_key": row["page_key"],
        "slide_index": row["slide_index"],
        "page_loaded": page_loaded,
        "final_url": final_url,
        "title": title,
        "signin_redirect": is_signin_redirect(final_url, title),
        "svg_found": svg_count > 0,
        "svg_count": svg_count,
        "aria_label_count": len(aria_labels),
        "text_length": len(slide_text),
        "snippet_count": len(keyword_contexts),
        "matched_keywords": sorted({context["keyword"] for context in keyword_contexts}),
        "keyword_context_snippets": keyword_contexts,
        "deadline_text_candidates": extract_deadline_candidates(slide_text),
        "error": error,
    }


def open_slide_and_collect(
    page: Any,
    row: dict[str, Any],
    goto_timeout_ms: int,
    wait_ms: int,
    manual_login_wait_ms: int,
    remaining_snippets: int,
    snippets_per_slide: int,
    snippet_chars: int,
) -> dict[str, Any]:
    try:
        page.goto(row["slide_url"], wait_until="domcontentloaded", timeout=goto_timeout_ms)
        page.wait_for_timeout(wait_ms)
        title = page.title()
        final_url = page.url
        if manual_login_wait_ms > 0 and is_signin_redirect(final_url, title):
            page.wait_for_timeout(manual_login_wait_ms)
            title = page.title()
            final_url = page.url
        dom_summary = collect_svg_aria_labels_from_page(page)
        result = build_slide_result(
            row=row,
            page_loaded=True,
            final_url=final_url,
            title=title,
            svg_count=dom_summary["svg_count"],
            aria_labels=dom_summary["aria_labels"],
            max_snippets=remaining_snippets,
            snippets_per_slide=snippets_per_slide,
            snippet_chars=snippet_chars,
        )
        result["frame_count"] = dom_summary["frame_count"]
        result["frame_errors"] = dom_summary["frame_errors"]
        return result
    except Exception as exc:
        return build_slide_result(
            row=row,
            page_loaded=False,
            final_url=getattr(page, "url", ""),
            title="",
            svg_count=0,
            aria_labels=[],
            max_snippets=0,
            snippets_per_slide=0,
            snippet_chars=snippet_chars,
            error=f"{type(exc).__name__}: {exc}",
        )


def probe_moocs_collect_slide_svg_text_playwright(
    probe_json: Path,
    db_path: Path,
    user_data_dir: Path,
    course_codes: list[str] | None = None,
    page_keys: list[str] | None = None,
    limit: int = 3,
    max_snippets: int = 20,
    snippets_per_slide: int = 3,
    snippet_chars: int = 300,
    goto_timeout_ms: int = 30000,
    wait_ms: int = 5000,
    manual_login_wait_ms: int = 0,
) -> dict[str, Any]:
    if limit < 0:
        raise ValueError("limit must be zero or greater")
    if max_snippets < 0:
        raise ValueError("max_snippets must be zero or greater")
    if snippets_per_slide < 0:
        raise ValueError("snippets_per_slide must be zero or greater")
    if snippet_chars < 0:
        raise ValueError("snippet_chars must be zero or greater")

    resolved_db_path = db_path.expanduser().resolve()
    resolved_user_data_dir = user_data_dir.expanduser().resolve()
    aio_pages = load_aio_page_keys(probe_json)
    selected_keys = filter_keys(
        aio_pages["unique_keys"],
        page_keys or [],
        course_codes or [],
    )

    with closing(open_readonly_database(resolved_db_path)) as connection:
        slide_rows = fetch_slide_url_rows(connection, selected_keys)

    results: list[dict[str, Any]] = []
    total_snippets = 0
    resolved_user_data_dir.mkdir(parents=True, exist_ok=True)
    with playwright_runner() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(resolved_user_data_dir),
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            for row in slide_rows[:limit]:
                remaining_snippets = max(0, max_snippets - total_snippets)
                result = open_slide_and_collect(
                    page=page,
                    row=row,
                    goto_timeout_ms=goto_timeout_ms,
                    wait_ms=wait_ms,
                    manual_login_wait_ms=manual_login_wait_ms,
                    remaining_snippets=remaining_snippets,
                    snippets_per_slide=snippets_per_slide,
                    snippet_chars=snippet_chars,
                )
                total_snippets += int(result["snippet_count"])
                results.append(result)
        finally:
            context.close()

    aria_label_result_count = sum(1 for result in results if result["aria_label_count"] > 0)
    return {
        "probe_json": str(probe_json.expanduser().resolve()),
        "db_path": str(resolved_db_path),
        "user_data_dir": str(resolved_user_data_dir),
        "total_aio_pages": aio_pages["generated_key_count"],
        "unique_aio_page_keys": len(aio_pages["unique_keys"]),
        "selected_aio_page_keys": len(selected_keys),
        "matched_slide_urls": len(slide_rows),
        "opened_slide_urls": len(results),
        "page_loaded_count": sum(1 for result in results if result["page_loaded"]),
        "signin_redirect_count": sum(1 for result in results if result["signin_redirect"]),
        "svg_found_count": sum(1 for result in results if result["svg_found"]),
        "aria_label_result_count": aria_label_result_count,
        "success": aria_label_result_count > 0,
        "total_keyword_snippets": total_snippets,
        "results": results,
        "safety": {
            "cookies_read": False,
            "tokens_read": False,
            "passwords_read": False,
            "storage_state_saved": False,
            "embed_html_full_text_printed": False,
            "embed_html_saved": False,
            "raw_svg_printed": False,
            "raw_svg_saved": False,
            "slide_images_saved": False,
            "slide_full_text_printed": False,
            "ocr_used": False,
            "tantivy_index_read": False,
            "sensitive_files_read": False,
        },
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    report = probe_moocs_collect_slide_svg_text_playwright(
        probe_json=args.probe_json,
        db_path=args.db_path,
        user_data_dir=args.user_data_dir,
        course_codes=args.course_code,
        page_keys=args.page_key,
        limit=args.limit,
        max_snippets=args.max_snippets,
        snippets_per_slide=args.snippets_per_slide,
        snippet_chars=args.snippet_chars,
        goto_timeout_ms=args.goto_timeout_ms,
        wait_ms=args.wait_ms,
        manual_login_wait_ms=args.manual_login_wait_ms,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
