import json

from playwright.sync_api import sync_playwright


URL = "https://moocs.iniad.org/courses/2026/COT101/07-1/01"
PROFILE = "data/probe/moocs_profile_api_diag2"
SELECTORS = [
    ".content-wrapper section.content",
    "section.content",
    ".content-wrapper",
    "main",
    "article",
    "body",
    "iframe",
]


with sync_playwright() as playwright:
    context = playwright.chromium.launch_persistent_context(PROFILE, headless=False)
    page = context.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    result = {
        "url": page.url,
        "title": page.title(),
        "selectors": {},
    }
    for selector in SELECTORS:
        result["selectors"][selector] = page.locator(selector).evaluate_all(
            """(elements) => elements.map((element) => ({
                tag: element.tagName,
                className: element.className,
                src: element.getAttribute("src"),
                text: (element.innerText || element.textContent || "")
                    .trim()
                    .replace(/\\s+/g, " ")
                    .slice(0, 500)
            }))"""
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    context.close()
