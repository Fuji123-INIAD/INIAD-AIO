import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


TARGET = os.getenv("MOOCS_AUTH_DIAG_TARGET", "https://moocs.iniad.org/courses/2026/COT101/01-1/01")
PROFILE = os.getenv("MOOCS_AUTH_DIAG_PROFILE", "data/probe/moocs_profile")
OUT = Path(os.getenv("MOOCS_AUTH_DIAG_OUT", "data/probe/moocs_auth_compare_existing_profile.json"))
LOGIN_WAIT_SECONDS = int(os.getenv("MOOCS_AUTH_DIAG_LOGIN_WAIT_SECONDS", "0"))


def redact_cookie(cookie):
    return {
        key: cookie.get(key)
        for key in ("name", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
    }


def storage_keys(page):
    try:
        return page.evaluate(
            """() => ({
                localStorage: Object.keys(window.localStorage || {}).sort(),
                sessionStorage: Object.keys(window.sessionStorage || {}).sort(),
                href: location.href,
                origin: location.origin,
                title: document.title
            })"""
        )
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def run(headless, wait_for_login=False):
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(PROFILE, headless=headless)
        page = context.new_page()
        try:
            page.goto(TARGET, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            if wait_for_login and "/signin" in urlparse(page.url).path and LOGIN_WAIT_SECONDS > 0:
                deadline = time.monotonic() + LOGIN_WAIT_SECONDS
                while time.monotonic() < deadline:
                    page.goto(TARGET, wait_until="domcontentloaded", timeout=30000)
                    if "/signin" not in urlparse(page.url).path:
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except PlaywrightTimeoutError:
                            pass
                        break
                    time.sleep(5)
            state = context.storage_state()
            final_url = page.url
            return {
                "headless": headless,
                "requested_url": TARGET,
                "final_url": final_url,
                "final_path": urlparse(final_url).path,
                "title": page.title(),
                "current_storage_keys": storage_keys(page),
                "cookies": [
                    redact_cookie(cookie)
                    for cookie in context.cookies(
                        ["https://moocs.iniad.org", "https://accounts.iniad.org"]
                    )
                ],
                "storage_state_cookie_names": sorted(
                    [(cookie.get("domain"), cookie.get("name")) for cookie in state.get("cookies", [])]
                ),
                "storage_state_origins": [
                    (
                        origin.get("origin"),
                        sorted(item.get("name") for item in origin.get("localStorage", [])),
                    )
                    for origin in state.get("origins", [])
                ],
            }
        finally:
            context.close()


results = [
    run(False, wait_for_login=True),
    run(False),
    run(True),
    run(False),
]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
print("wrote", OUT)
