import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


TARGET = os.getenv("MOOCS_AUTH_DIAG_TARGET", "https://moocs.iniad.org/courses/2026/COT101/01-1/01")
PROFILE = os.getenv("MOOCS_AUTH_DIAG_PROFILE", "data/probe/moocs_profile_storage_diag")
STATE_PATH = Path(os.getenv("MOOCS_AUTH_DIAG_STATE", "data/probe/moocs_storage_state_before_headless.json"))
OUT = Path(os.getenv("MOOCS_AUTH_DIAG_OUT", "data/probe/moocs_storage_state_compare.json"))
LOGIN_WAIT_SECONDS = int(os.getenv("MOOCS_AUTH_DIAG_LOGIN_WAIT_SECONDS", "300"))
CREATE_ONLY = os.getenv("MOOCS_AUTH_DIAG_CREATE_ONLY", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def redact_cookie(cookie):
    return {
        key: cookie.get(key)
        for key in ("name", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
    }


def summarize_state(state):
    return {
        "cookie_names": sorted(
            [(cookie.get("domain"), cookie.get("name")) for cookie in state.get("cookies", [])]
        ),
        "origins": [
            (
                origin.get("origin"),
                sorted(item.get("name") for item in origin.get("localStorage", [])),
            )
            for origin in state.get("origins", [])
        ],
    }


def page_summary(page, context):
    state = context.storage_state()
    return {
        "final_url": page.url,
        "final_path": urlparse(page.url).path,
        "title": page.title(),
        "storage": page.evaluate(
            """() => ({
                localStorage: Object.keys(window.localStorage || {}).sort(),
                sessionStorage: Object.keys(window.sessionStorage || {}).sort()
            })"""
        ),
        "cookies": [
            redact_cookie(cookie)
            for cookie in context.cookies(["https://moocs.iniad.org", "https://accounts.iniad.org"])
        ],
        "state_summary": summarize_state(state),
    }


def goto_target(page):
    try:
        page.goto(TARGET, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightError:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        pass


def create_state(playwright):
    context = playwright.chromium.launch_persistent_context(PROFILE, headless=False)
    page = context.new_page()
    try:
        goto_target(page)
        deadline = time.monotonic() + LOGIN_WAIT_SECONDS
        while "/signin" in urlparse(page.url).path and time.monotonic() < deadline:
            time.sleep(5)
            goto_target(page)
        result = page_summary(page, context)
        if "/signin" not in urlparse(page.url).path:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STATE_PATH))
            result["storage_state_saved"] = True
            result["storage_state_path"] = str(STATE_PATH)
        else:
            result["storage_state_saved"] = False
        return result
    finally:
        context.close()


def run_storage_state(playwright, headless):
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(STATE_PATH))
    page = context.new_page()
    try:
        goto_target(page)
        result = page_summary(page, context)
        result["headless"] = headless
        return result
    finally:
        context.close()
        browser.close()


with sync_playwright() as playwright:
    created = create_state(playwright)
    results = {
        "persistent_headed_create_state": created,
        "storage_state_headed": None if CREATE_ONLY else run_storage_state(playwright, False) if STATE_PATH.exists() else None,
        "storage_state_headless": None if CREATE_ONLY else run_storage_state(playwright, True) if STATE_PATH.exists() else None,
    }

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
print("wrote", OUT)
