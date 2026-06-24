"""Inspect a few authenticated MOOCs pages without saving HTML or credentials."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT_DIR / "data" / "probe" / "moocs_profile"
DEFAULT_TARGETS = (
    (
        "COT101 通常課題: 課題1-1-1",
        "https://moocs.iniad.org/courses/2026/COT101/01-1/06",
    ),
    (
        "COT101 課題解説",
        "https://moocs.iniad.org/courses/2026/COT101/01-1/review",
    ),
    (
        "COT105 Report: レポート課題",
        "https://moocs.iniad.org/courses/2026/COT105/01/report",
    ),
    (
        "COT105 Quiz: Part1 Quiz",
        "https://moocs.iniad.org/courses/2026/COT105/08/02",
    ),
)
KEYWORD_RE = re.compile(
    r"deadline|due|closing|close|submit|submission|"
    r"締切|期限|提出期限|提出|メール|mail",
    re.IGNORECASE,
)
CONTENT_SELECTORS = (
    ".content-wrapper section.content",
    "section.content",
    ".content-wrapper",
    "main",
    "article",
    "body",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a small fixed set of authenticated MOOCs pages."
    )
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--storage-state",
        type=Path,
        help="Use an existing Playwright storage-state file instead of a profile.",
    )
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use only for diagnostics; MOOCs authentication may reject headless Chromium.",
    )
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Inspect an explicit URL instead of the four default representative pages.",
    )
    return parser.parse_args()


def compact_text(value: str) -> str:
    return " ".join((value or "").split())


def truncate(value: str, limit: int) -> str:
    value = compact_text(value)
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def keyword_contexts(text: str, radius: int = 100) -> list[str]:
    contexts: list[str] = []
    compact = compact_text(text)
    for match in KEYWORD_RE.finditer(compact):
        start = max(0, match.start() - radius)
        end = min(len(compact), match.end() + radius)
        context = compact[start:end]
        if context not in contexts:
            contexts.append(context)
    return contexts[:20]


def content_scope(page):
    for selector in CONTENT_SELECTORS:
        locator = page.locator(selector)
        if locator.count() and compact_text(locator.first.inner_text(timeout=3000)):
            return locator.first, selector
    return page.locator("body"), "body"


def safe_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https", "mailto"}:
        return None
    if parsed.scheme == "mailto":
        return "mailto:" + parsed.path
    return parsed._replace(fragment="").geturl()


def inspect_links(scope, page_url: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    locator = scope.locator("a[href]")
    for index in range(min(locator.count(), 100)):
        link = locator.nth(index)
        href = safe_url(page_url, link.get_attribute("href"))
        if not href:
            continue
        text = truncate(link.inner_text(timeout=1000), 160)
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            {
                "text": text or None,
                "url": href,
                "external": urlparse(href).hostname not in {None, "moocs.iniad.org"},
                "mailto": href.startswith("mailto:"),
            }
        )
    return links[:50]


def inspect_forms(scope, page_url: str) -> list[dict[str, Any]]:
    forms: list[dict[str, Any]] = []
    locator = scope.locator("form")
    for index in range(locator.count()):
        form = locator.nth(index)
        input_types = []
        inputs = form.locator("input")
        for input_index in range(inputs.count()):
            input_type = (inputs.nth(input_index).get_attribute("type") or "text").lower()
            input_types.append(input_type)
        forms.append(
            {
                "method": (form.get_attribute("method") or "get").lower(),
                "action": safe_url(page_url, form.get_attribute("action") or page_url),
                "input_types": input_types,
                "button_texts": [
                    truncate(form.locator("button").nth(i).inner_text(timeout=1000), 120)
                    for i in range(form.locator("button").count())
                ],
            }
        )
    return forms


def inspect_page(page, label: str, target_url: str, timeout_ms: int) -> dict[str, Any]:
    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10000))
    except Exception:
        pass

    scope, scope_selector = content_scope(page)
    visible_text = compact_text(scope.inner_text(timeout=3000))
    links = inspect_links(scope, page.url)
    forms = inspect_forms(scope, page.url)
    buttons = scope.locator("button, input[type='submit'], input[type='button']")
    button_summaries = []
    for index in range(buttons.count()):
        button = buttons.nth(index)
        button_summaries.append(
            {
                "tag": button.evaluate("element => element.tagName.toLowerCase()"),
                "type": button.get_attribute("type"),
                "text": truncate(
                    button.inner_text(timeout=1000)
                    or button.get_attribute("value")
                    or button.get_attribute("aria-label")
                    or "",
                    120,
                ),
            }
        )

    time_elements = []
    times = scope.locator("time")
    for index in range(times.count()):
        item = times.nth(index)
        time_elements.append(
            {
                "text": truncate(item.inner_text(timeout=1000), 160),
                "datetime": item.get_attribute("datetime"),
            }
        )

    frames = scope.locator("iframe[src]")
    non_google_frames = []
    for index in range(frames.count()):
        src = safe_url(page.url, frames.nth(index).get_attribute("src"))
        if src and "docs.google.com/presentation" not in src:
            non_google_frames.append(src)

    return {
        "label": label,
        "requested_url": target_url,
        "final_url": page.url,
        "document_title": page.title(),
        "signin_redirect": "/signin" in urlparse(page.url).path,
        "content_selector": scope_selector,
        "visible_text_length": len(visible_text),
        "visible_text_excerpt": truncate(visible_text, 1800),
        "keyword_contexts": keyword_contexts(visible_text),
        "form_count": len(forms),
        "forms": forms,
        "button_count": len(button_summaries),
        "buttons": button_summaries[:30],
        "time_elements": time_elements,
        "mailto_links": [link for link in links if link["mailto"]],
        "external_links": [link for link in links if link["external"]],
        "ordinary_links": links,
        "non_google_iframe_urls": non_google_frames,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    profile_dir = args.profile_dir.resolve()
    storage_state = args.storage_state.resolve() if args.storage_state else None
    if storage_state is not None:
        if not storage_state.is_file():
            raise FileNotFoundError(f"MOOCs storage state not found: {storage_state}")
    elif not profile_dir.is_dir():
        raise FileNotFoundError(f"MOOCs profile directory not found: {profile_dir}")

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        raise RuntimeError("Playwright is not installed in this Python environment") from error

    targets = (
        tuple((f"explicit URL {index}", url) for index, url in enumerate(args.url, 1))
        if args.url
        else DEFAULT_TARGETS
    )

    results = []
    with sync_playwright() as playwright:
        browser = None
        if storage_state is not None:
            browser = playwright.chromium.launch(headless=args.headless)
            context = browser.new_context(storage_state=str(storage_state))
        else:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=args.headless,
            )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            for label, target_url in targets:
                try:
                    results.append(inspect_page(page, label, target_url, args.timeout_ms))
                except Exception as error:
                    results.append(
                        {
                            "label": label,
                            "requested_url": target_url,
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
        finally:
            context.close()
            if browser is not None:
                browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
