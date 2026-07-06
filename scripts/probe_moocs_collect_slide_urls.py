"""Inspect slides.url patterns from MOOCs-Collect db.sqlite."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.moocs_collect_text import (
    load_metadata_records,
    open_readonly_database,
    parse_slide_url_kind,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe MOOCs-Collect slide URL patterns.")
    parser.add_argument("db_path", type=Path, help="Path to MOOCs-Collect db.sqlite.")
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("--try-playwright", action="store_true")
    return parser.parse_args(argv)


def probe_moocs_collect_slide_urls(
    db_path: Path,
    *,
    sample_limit: int = 10,
    try_playwright: bool = False,
) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    resolved = db_path.expanduser().resolve()
    with open_readonly_database(resolved) as connection:
        records = load_metadata_records(
            connection,
            limit=None,
            course_code=None,
            lecture_key=None,
        )

    host_counts: Counter[str] = Counter()
    path_pattern_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    samples = []
    for record in records:
        kind = parse_slide_url_kind(record.slide_url)
        host_counts[kind["host"] or "(none)"] += 1
        path_pattern_counts[kind["path_pattern"]] += 1
        for key in ("is_google_slides", "is_moocs", "is_pdf", "is_file_url"):
            if kind[key]:
                kind_counts[key] += 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "course_code": record.course_code,
                    "lecture_key": record.lecture_key,
                    "page_key": record.page_key,
                    "slide_index": record.slide_index,
                    "pdf_filename": Path(record.pdf_path).name if record.pdf_path else None,
                    "url": record.slide_url,
                    "url_kind": {
                        key: value
                        for key, value in kind.items()
                        if key != "url"
                    },
                }
            )

    playwright_probe = []
    if try_playwright:
        playwright_probe, playwright_warnings = probe_playwright_samples(samples)
        warnings.extend(playwright_warnings)
    else:
        warnings.append(
            {
                "message": (
                    "Playwright live DOM probing was not requested. "
                    "Use --try-playwright only in an authenticated local session."
                )
            }
        )

    return {
        "status": "ok",
        "db_path": str(resolved),
        "slide_count": len(records),
        "url_host_counts": dict(sorted(host_counts.items())),
        "url_path_pattern_counts": dict(sorted(path_pattern_counts.items())),
        "url_kind_counts": dict(sorted(kind_counts.items())),
        "samples": samples,
        "playwright_probe": playwright_probe,
        "warnings": warnings,
        "safety": {
            "cookies_written": False,
            "storage_state_written": False,
            "browser_profile_committed": False,
        },
    }


def probe_playwright_samples(samples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return [], [{"message": f"Playwright is not available: {type(exc).__name__}: {exc}"}]

    results = []
    warnings = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            for sample in samples[:3]:
                url = sample.get("url")
                if not url:
                    continue
                result = {"url": url, "opened": False, "dom_text_length": 0, "svg_text_count": 0, "aria_label_count": 0}
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    result["opened"] = True
                    text = page.locator("body").inner_text(timeout=3000)
                    result["dom_text_length"] = len(" ".join(text.split()))
                    result["svg_text_count"] = page.locator("svg text").count()
                    result["aria_label_count"] = page.locator("[aria-label]").count()
                except Exception as exc:
                    result["warning"] = f"{type(exc).__name__}: {exc}"
                results.append(result)
            browser.close()
    except Exception as exc:
        warnings.append({"message": f"Playwright probing failed: {type(exc).__name__}: {exc}"})
    return results, warnings


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = probe_moocs_collect_slide_urls(
        args.db_path,
        sample_limit=max(0, args.sample_limit),
        try_playwright=bool(args.try_playwright),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
