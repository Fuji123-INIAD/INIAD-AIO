from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ModuleNotFoundError:
    Page = object
    PlaywrightError = Exception
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


BASE_DIR = Path(__file__).resolve().parent.parent
MOOCS_COURSES_URL = "https://moocs.iniad.org/courses"
DEFAULT_STORAGE_STATE = BASE_DIR / "data" / "probe" / "moocs_storage_state.json"
DEFAULT_OUTPUT_PATH = BASE_DIR / "data" / "probe" / "moocs_courses.json"
DEFAULT_DETAILS_OUTPUT_PATH = BASE_DIR / "data" / "probe" / "moocs_course_details.json"
DEFAULT_LINKS_DEBUG_OUTPUT_PATH = BASE_DIR / "data" / "probe" / "moocs_course_links_debug.json"
DEFAULT_LESSON_DEBUG_OUTPUT_PATH = BASE_DIR / "data" / "probe" / "moocs_lesson_debug.json"
DEFAULT_LINKS_DEBUG_COURSE_URL = "https://moocs.iniad.org/courses/2026/COT101"
DEFAULT_CONTENT_CHECK_URL = "https://moocs.iniad.org/courses/2026/COT101/01-1/01"
DEFAULT_PROFILE_DIR = BASE_DIR / "data" / "probe" / "moocs_profile"

COURSE_CARD_SELECTOR = ".well"
COURSE_YEAR_ARCHIVE_RE = re.compile(r"^/courses/\d{4}$")
GOOGLE_SLIDES_IFRAME_SELECTOR = "iframe[src*='docs.google.com/presentation']"
DOCUMENT_TITLE_SUFFIX_RE = re.compile(r"\s*[:|-]\s*INIAD MOOCs\s*$", re.IGNORECASE)
BOOKMARK_TITLE_SUFFIX_RE = re.compile(r"\s*(Bookmark|ブックマーク)\s*$", re.IGNORECASE)
UI_TITLE_TEXTS = {
    "Toggle navigation",
    "Settings",
    "Sign out",
    "藤田 優希",
    "ブックマーク",
    "INIAD MOOCs",
    "Homepage",
    "Contact",
}

# v0.2+ will need to inspect slide materials inside each course. INIAD++ research found no
# stable MOOCs internal API, so downstream providers should expect Google Slides/Viewer frames.
VIEWER_FRAME_SELECTORS = (
    "iframe[src*='docs.google.com/presentation']",
    "iframe[src*='docs.google.com/document']",
    "iframe[src*='drive.google.com/file']",
    "iframe[src*='viewer']",
)
CONTENT_SELECTORS = (
    ".content-wrapper section.content",
    "section.content",
    ".content-wrapper",
    "main",
    "article",
    "body",
)
EVIDENCE_KEYWORD_RE = re.compile(
    r"期限|締切|締め切り|提出|回答|受け付け|受付|Quiz|Report|"
    r"deadline|due|submit|submission|answer|accepting|accepted",
    re.IGNORECASE,
)
DEADLINE_HINT_RE = re.compile(
    r"期限|締切|締め切り|due|deadline|"
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}|"
    r"\d{1,2}月\d{1,2}日|"
    r"\d{1,2}:\d{2}|"
    r"今日|明日|翌日|今週|来週|まで|以内",
    re.IGNORECASE,
)
ACCEPTING_STATUS_RE = re.compile(
    r"受け付け|受付|受付中|受付終了|提出済|未提出|"
    r"accepting|accepted|closed|submitted|not submitted",
    re.IGNORECASE,
)
SUBMIT_BUTTON_RE = re.compile(r"提出|回答|送信|submit|answer", re.IGNORECASE)
EXTRACTED_TEXT_LIMIT = 3000
CONTEXT_RADIUS = 100
MAX_CONTEXTS = 20
MAX_BUTTONS = 30
MAX_IFRAME_URLS = 30
CONTENT_TEXT_NOISE_RE = re.compile(
    r"(?:[«»]\s*)?\b(?:Bookmark|Previous|Next|Toggle navigation|Settings|Sign out)\b(?:\s*[«»])?"
    r"|ブックマーク",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CourseProbeRecord:
    course_title: str
    course_url: str
    retrieval_method: str
    fetched_at: str


@dataclass(frozen=True)
class CourseMaterialProbeRecord:
    material_type: str
    material_url: str
    retrieval_method: str


@dataclass(frozen=True)
class CoursePageProbeRecord:
    page_title: str
    page_url: str
    materials: list[CourseMaterialProbeRecord]
    extracted_text: str | None = None
    keyword_contexts: list[str] | None = None
    buttons: list[dict[str, object]] | None = None
    submit_button_present: bool | None = None
    deadline_text_candidates: list[str] | None = None
    accepting_status_text: str | None = None
    non_google_iframe_urls: list[str] | None = None
    signin_redirect: bool | None = None
    content_fetched_at: str | None = None
    content_retrieval_method: str | None = None


@dataclass(frozen=True)
class CourseLessonProbeRecord:
    lesson_title: str
    lesson_url: str
    pages: list[CoursePageProbeRecord]


@dataclass(frozen=True)
class CourseDetailProbeRecord:
    course_title: str
    course_url: str
    lessons: list[CourseLessonProbeRecord]
    fetched_at: str


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_course_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return path.startswith("/courses/") and path != "/courses" and not COURSE_YEAR_ARCHIVE_RE.match(path)


def normalize_space(value: str) -> str:
    return " ".join(value.split())


def clean_evidence_text(value: str) -> str:
    text = normalize_space(value)
    text = CONTENT_TEXT_NOISE_RE.sub(" ", text)
    return normalize_space(text)


def truncate_text(value: str, limit: int) -> str:
    text = normalize_space(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def clean_page_title_text(value: str) -> str:
    title = normalize_space(value)
    title = BOOKMARK_TITLE_SUFFIX_RE.sub("", title)
    return normalize_space(title)


def is_usable_page_title(value: str) -> bool:
    title = clean_page_title_text(value)
    return bool(title) and title not in UI_TITLE_TEXTS


def clean_document_title(value: str) -> str:
    title = clean_page_title_text(value)
    title = DOCUMENT_TITLE_SUFFIX_RE.sub("", title)
    return clean_page_title_text(title)


def extract_content_page_title(page: Page, page_url: str) -> str:
    selectors = (
        ".content-wrapper section.content h2",
        "section.content h2",
        ".content-wrapper h2",
        ".content-wrapper section.content h1",
        "section.content h1",
        ".content-wrapper h1",
        ".content-wrapper section.content h3",
        "section.content h3",
        ".content-wrapper h3",
        ".content-wrapper section.content h4",
        "section.content h4",
        ".content-wrapper h4",
    )
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(locator.count()):
            try:
                title = clean_page_title_text(locator.nth(index).inner_text(timeout=1000))
            except PlaywrightError as exc:
                logging.debug("page title candidate failed selector=%r index=%s error=%s", selector, index, exc)
                continue
            if is_usable_page_title(title):
                return title

    document_title = clean_document_title(page.title())
    if is_usable_page_title(document_title):
        return document_title

    return fallback_title_from_url(page_url)


def content_scope(page: Page):
    for selector in CONTENT_SELECTORS:
        locator = page.locator(selector)
        try:
            if locator.count() and normalize_space(locator.first.inner_text(timeout=3000)):
                return locator.first, selector
        except PlaywrightError as exc:
            logging.debug("content selector failed selector=%r error=%s", selector, exc)
            continue
    return page.locator("body"), "body"


def text_contexts(text: str, pattern: re.Pattern[str], radius: int = CONTEXT_RADIUS, limit: int = MAX_CONTEXTS) -> list[str]:
    compact = clean_evidence_text(text)
    contexts: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(compact):
        start = max(0, match.start() - radius)
        end = min(len(compact), match.end() + radius)
        context = compact[start:end]
        if context and context not in seen:
            seen.add(context)
            contexts.append(context)
        if len(contexts) >= limit:
            break
    return contexts


def extract_keyword_contexts_from_text(text: str) -> list[str]:
    return text_contexts(text, EVIDENCE_KEYWORD_RE)


def extract_deadline_text_candidates_from_text(text: str) -> list[str]:
    return text_contexts(text, DEADLINE_HINT_RE)


def extract_accepting_status_from_text(text: str) -> str | None:
    contexts = text_contexts(text, ACCEPTING_STATUS_RE, radius=80, limit=1)
    return contexts[0] if contexts else None


def safe_http_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    return parsed._replace(fragment="").geturl()


def is_google_frame_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname.endswith("docs.google.com") or hostname.endswith("drive.google.com")


def extract_page_html_evidence(page: Page, fetched_at: str) -> dict[str, object]:
    scope, scope_selector = content_scope(page)
    try:
        visible_text = clean_evidence_text(scope.inner_text(timeout=3000))
    except PlaywrightError as exc:
        logging.warning("failed to extract content text selector=%r error=%s", scope_selector, exc)
        visible_text = ""

    buttons: list[dict[str, object]] = []
    button_locator = scope.locator("button, input[type='submit'], input[type='button']")
    for index in range(min(button_locator.count(), MAX_BUTTONS)):
        button = button_locator.nth(index)
        try:
            tag_name = button.evaluate("element => element.tagName.toLowerCase()")
            button_type = (button.get_attribute("type") or "").lower() or None
            disabled = bool(
                button.evaluate(
                    "element => Boolean(element.disabled || element.getAttribute('aria-disabled') === 'true')"
                )
            )
            text = truncate_text(
                button.inner_text(timeout=1000)
                or button.get_attribute("aria-label")
                or button.get_attribute("title")
                or "",
                120,
            )
        except PlaywrightError as exc:
            logging.debug("button evidence extraction failed index=%s error=%s", index, exc)
            continue
        buttons.append(
            {
                "text": text or None,
                "type": button_type or tag_name,
                "disabled": disabled,
            }
        )

    non_google_iframe_urls: list[str] = []
    iframes = scope.locator("iframe[src]")
    for index in range(min(iframes.count(), MAX_IFRAME_URLS)):
        try:
            src = safe_http_url(page.url, iframes.nth(index).get_attribute("src"))
        except PlaywrightError as exc:
            logging.debug("iframe evidence extraction failed index=%s error=%s", index, exc)
            continue
        if src and not is_google_frame_url(src) and src not in non_google_iframe_urls:
            non_google_iframe_urls.append(src)

    submit_button_present = any(
        SUBMIT_BUTTON_RE.search(str(button.get("text") or ""))
        or SUBMIT_BUTTON_RE.search(str(button.get("type") or ""))
        for button in buttons
    )

    return {
        "extracted_text": truncate_text(visible_text, EXTRACTED_TEXT_LIMIT) or None,
        "keyword_contexts": extract_keyword_contexts_from_text(visible_text),
        "buttons": buttons,
        "submit_button_present": submit_button_present,
        "deadline_text_candidates": extract_deadline_text_candidates_from_text(visible_text),
        "accepting_status_text": extract_accepting_status_from_text(visible_text),
        "non_google_iframe_urls": non_google_iframe_urls,
        "signin_redirect": "/signin" in urlparse(page.url).path,
        "content_fetched_at": fetched_at,
        "content_retrieval_method": f"dom:{scope_selector}",
    }


def require_storage_state(storage_state: Path) -> Path:
    resolved = storage_state.resolve()
    if not resolved.exists():
        raise FileNotFoundError(
            f"storage_state not found: {resolved}. "
            "Create it with Playwright after logging in to MOOCs."
        )
    return resolved


def playwright_runner():
    if sync_playwright is None:
        raise RuntimeError(
            "playwright is not installed in this Python environment. "
            "Activate .venv or run `pip install -r backend/requirements.txt`."
        )
    return sync_playwright()


def open_moocs_context(playwright, storage_state: Path, user_data_dir: Path | None, headless: bool):
    if user_data_dir is not None:
        if headless:
            raise RuntimeError(
                "MOOCs persistent profiles must not be opened with headless=true. "
                "Use --headed and a dedicated --user-data-dir instead."
            )
        resolved_user_data_dir = user_data_dir.resolve()
        resolved_user_data_dir.mkdir(parents=True, exist_ok=True)
        logging.info("using persistent browser user_data_dir=%s", resolved_user_data_dir)
        return playwright.chromium.launch_persistent_context(
            user_data_dir=str(resolved_user_data_dir),
            headless=headless,
        )

    resolved_storage_state = require_storage_state(storage_state)
    logging.info("using storage_state=%s", resolved_storage_state)
    browser = playwright.chromium.launch(headless=headless)
    return browser.new_context(storage_state=str(resolved_storage_state))


def close_moocs_context(context) -> None:
    browser = context.browser
    context.close()
    if browser is not None:
        try:
            browser.close()
        except PlaywrightError:
            logging.debug("browser was already closed with context")


def wait_for_manual_login_if_needed(page: Page, target_url: str, user_data_dir: Path | None, headless: bool, timeout_ms: int) -> None:
    if user_data_dir is None or headless or "/signin" not in urlparse(page.url).path:
        return

    logging.warning(
        "persistent user_data_dir is not logged in yet. Complete login in the opened browser, then press Enter here."
    )
    try:
        input("MOOCs login complete? Press Enter to continue...")
    except EOFError:
        logging.warning("stdin is not interactive; continuing without manual login wait")
        return

    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logging.warning("networkidle wait timed out after manual login; continuing with current DOM")


def visit_moocs_url(
    page: Page,
    url: str,
    profile_dir: Path | None,
    headless: bool,
    timeout_ms: int,
    wait_for_login_input: bool = True,
) -> dict[str, object]:
    logging.info("opening %s", url)
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logging.warning("networkidle wait timed out for url=%s; continuing with current DOM", url)
    if wait_for_login_input:
        wait_for_manual_login_if_needed(page, url, profile_dir, headless, timeout_ms)

    current_url = page.url
    redirected_to_signin = "/signin" in urlparse(current_url).path or "/auth/" in urlparse(current_url).path
    content_title = ""
    if not redirected_to_signin:
        try:
            content_title = extract_content_page_title(page, current_url)
        except PlaywrightError as exc:
            logging.debug("content title extraction failed url=%s error=%s", current_url, exc)

    return {
        "requested_url": url,
        "current_url": current_url,
        "ok": not redirected_to_signin,
        "redirected_to_signin": redirected_to_signin,
        "title": clean_document_title(page.title()),
        "content_title": content_title,
    }


def check_moocs_url_access(
    storage_state: Path,
    profile_dir: Path | None,
    url: str,
    headless: bool,
    timeout_ms: int,
) -> dict[str, object]:
    with playwright_runner() as playwright:
        context = open_moocs_context(playwright, storage_state, profile_dir, headless)
        page = context.new_page()
        try:
            return visit_moocs_url(page, url, profile_dir, headless, timeout_ms)
        finally:
            close_moocs_context(context)


def save_storage_state_from_profile(
    storage_state: Path,
    profile_dir: Path,
    check_url: str,
    headless: bool,
    timeout_ms: int,
    login_wait_ms: int,
) -> dict[str, object]:
    with playwright_runner() as playwright:
        context = open_moocs_context(playwright, storage_state, profile_dir, headless)
        page = context.new_page()
        try:
            result = visit_moocs_url(
                page,
                check_url,
                profile_dir,
                headless,
                timeout_ms,
                wait_for_login_input=False,
            )
            if not result["ok"] and not headless and login_wait_ms > 0:
                logging.warning(
                    "MOOCs login is still required. Complete login in the opened browser; "
                    "waiting up to %sms for content access.",
                    login_wait_ms,
                )
                deadline = time.monotonic() + (login_wait_ms / 1000)
                while time.monotonic() < deadline:
                    try:
                        page.goto(check_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        current_url = page.url
                        if "/signin" not in urlparse(current_url).path and "/auth/" not in urlparse(current_url).path:
                            result = visit_moocs_url(
                                page,
                                check_url,
                                profile_dir,
                                headless,
                                timeout_ms,
                                wait_for_login_input=False,
                            )
                            break
                    except (PlaywrightTimeoutError, PlaywrightError) as exc:
                        logging.debug("login wait check failed url=%s error=%s", check_url, exc)
                    time.sleep(5)

            if not result["ok"]:
                logging.warning(
                    "MOOCs login was not confirmed; refusing to save storage_state=%s",
                    storage_state,
                )
                result["storage_state_saved"] = False
                result["storage_state_path"] = str(storage_state.resolve())
                return result

            storage_state.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(storage_state))
            logging.info("saved storage_state=%s", storage_state.resolve())
            result["storage_state_saved"] = True
            result["storage_state_path"] = str(storage_state.resolve())
            return result
        finally:
            close_moocs_context(context)


def material_to_dict(material: CourseMaterialProbeRecord) -> dict[str, str]:
    return {
        "material_type": material.material_type,
        "material_url": material.material_url,
        "retrieval_method": material.retrieval_method,
    }


def page_to_dict(page: CoursePageProbeRecord) -> dict[str, object]:
    return {
        "page_title": page.page_title,
        "page_url": page.page_url,
        "materials": [material_to_dict(material) for material in page.materials],
        "extracted_text": page.extracted_text,
        "keyword_contexts": page.keyword_contexts or [],
        "buttons": page.buttons or [],
        "submit_button_present": page.submit_button_present,
        "deadline_text_candidates": page.deadline_text_candidates or [],
        "accepting_status_text": page.accepting_status_text,
        "non_google_iframe_urls": page.non_google_iframe_urls or [],
        "signin_redirect": page.signin_redirect,
        "content_fetched_at": page.content_fetched_at,
        "content_retrieval_method": page.content_retrieval_method,
    }


def lesson_to_dict(lesson: CourseLessonProbeRecord) -> dict[str, object]:
    return {
        "lesson_title": lesson.lesson_title,
        "lesson_url": lesson.lesson_url,
        "pages": [page_to_dict(page) for page in lesson.pages],
    }


def course_detail_to_dict(detail: CourseDetailProbeRecord) -> dict[str, object]:
    return {
        "course_title": detail.course_title,
        "course_url": detail.course_url,
        "lessons": [lesson_to_dict(lesson) for lesson in detail.lessons],
        "fetched_at": detail.fetched_at,
    }


def load_course_records(path: Path) -> list[CourseProbeRecord]:
    raw_courses = json.loads(path.read_text(encoding="utf-8"))
    records: list[CourseProbeRecord] = []
    for index, raw_course in enumerate(raw_courses):
        course_title = normalize_space(str(raw_course.get("course_title", "")))
        course_url = normalize_space(str(raw_course.get("course_url", "")))
        if not course_title or not course_url:
            logging.warning("skip invalid course record index=%s record=%s", index, raw_course)
            continue

        records.append(
            CourseProbeRecord(
                course_title=course_title,
                course_url=course_url,
                retrieval_method=normalize_space(str(raw_course.get("retrieval_method", "json:moocs_courses"))),
                fetched_at=normalize_space(str(raw_course.get("fetched_at", ""))),
            )
        )

    return records


def course_code_from_url(url: str) -> str:
    segments = path_segments(url)
    return segments[-1] if segments else ""


def filter_courses_by_code(records: list[CourseProbeRecord], course_code: str | None) -> list[CourseProbeRecord]:
    if not course_code:
        return records

    normalized_course_code = course_code.strip().lower()
    return [
        record
        for record in records
        if course_code_from_url(record.course_url).lower() == normalized_course_code
    ]


def collect_course_link_debug(page: Page, course_url: str) -> dict[str, object]:
    viewer_frame_counts: dict[str, int] = {}
    for selector in VIEWER_FRAME_SELECTORS:
        viewer_frame_counts[selector] = page.locator(selector).count()

    links = page.locator("a[href]").evaluate_all(
        """(anchors, courseUrl) => anchors.map((anchor, index) => {
            const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
            const href = anchor.href || '';
            const text = normalize(anchor.innerText || anchor.textContent || anchor.getAttribute('aria-label') || anchor.getAttribute('title'));
            const className = anchor.getAttribute('class') || '';
            const normalizedCourseUrl = courseUrl.replace(/\\/$/, '');
            const normalizedHref = href.replace(/\\/$/, '');
            let path = '';
            try {
                path = new URL(href, window.location.href).pathname;
            } catch {
                path = '';
            }

            const candidateReasons = [];
            if (normalizedHref.startsWith(normalizedCourseUrl + '/')) {
                candidateReasons.push('same_course_subpage');
            }
            if (/material|lecture|lesson|slide|document|assignment|quiz|exam|homework|task|resource|content/i.test(href)) {
                candidateReasons.push('href_keyword');
            }
            if (/教材|資料|課題|スライド|講義|小テスト|テスト|レポート|宿題|Material|Slide|Assignment|Quiz|Lecture|Lesson|Resource/i.test(text)) {
                candidateReasons.push('text_keyword');
            }
            if (/btn|material|resource|assignment|lecture|lesson|list-group-item/i.test(className)) {
                candidateReasons.push('class_keyword');
            }

            return {
                index,
                href,
                text,
                tag: anchor.tagName.toLowerCase(),
                class: className,
                path,
                is_candidate: candidateReasons.length > 0,
                candidate_reasons: candidateReasons
            };
        })""",
        course_url,
    )

    selector_counts = {
        "a[href]": page.locator("a[href]").count(),
        "a[href*='/courses/']": page.locator("a[href*='/courses/']").count(),
        "a[href*='materials']": page.locator("a[href*='materials']").count(),
        "a[href*='assignments']": page.locator("a[href*='assignments']").count(),
        "a[href*='quizzes']": page.locator("a[href*='quizzes']").count(),
        "a[href*='lectures']": page.locator("a[href*='lectures']").count(),
        "a[href*='slides']": page.locator("a[href*='slides']").count(),
        "a[href*='docs.google.com']": page.locator("a[href*='docs.google.com']").count(),
        "iframe[src*='docs.google.com/presentation']": page.locator("iframe[src*='docs.google.com/presentation']").count(),
    }

    return {
        "course_url": course_url,
        "page_url": page.url,
        "page_title": page.title(),
        "reached_course_page": page.url.rstrip("/") == course_url.rstrip("/"),
        "login_redirect_detected": "/signin" in urlparse(page.url).path or "/auth/" in urlparse(page.url).path,
        "fetched_at": utc_now_iso(),
        "selector_counts": selector_counts,
        "viewer_frame_counts": viewer_frame_counts,
        "links": links,
    }


def collect_lesson_debug(page: Page, lesson_url: str) -> dict[str, object]:
    headings = page.locator("h1, h2, h3, h4").evaluate_all(
        """headings => headings.map((heading, index) => ({
            index,
            tag: heading.tagName.toLowerCase(),
            text: (heading.innerText || heading.textContent || '').replace(/\\s+/g, ' ').trim()
        })).filter(heading => heading.text)"""
    )

    iframes = page.locator("iframe").evaluate_all(
        """iframes => iframes.map((iframe, index) => ({
            index,
            src: iframe.src || iframe.getAttribute('src') || '',
            title: (iframe.getAttribute('title') || '').replace(/\\s+/g, ' ').trim(),
            class: iframe.getAttribute('class') || ''
        }))"""
    )

    links = page.locator("a[href]").evaluate_all(
        """anchors => anchors.map((anchor, index) => {
            const normalize = value => (value || '').replace(/\\s+/g, ' ').trim();
            const href = anchor.href || '';
            const text = normalize(anchor.innerText || anchor.textContent || anchor.getAttribute('aria-label') || anchor.getAttribute('title'));
            const className = anchor.getAttribute('class') || '';
            const candidateReasons = [];

            if (/docs\\.google\\.com|drive\\.google\\.com/i.test(href)) {
                candidateReasons.push('google_content');
            }
            if (/presentation|document|viewer|slide|material|resource|download|file|assignment|quiz|lesson|lecture|content/i.test(href)) {
                candidateReasons.push('href_keyword');
            }
            if (/スライド|資料|教材|課題|講義|小テスト|テスト|レポート|ダウンロード|Material|Slide|Document|Drive|Assignment|Quiz|Lecture|Lesson|Resource|Download/i.test(text)) {
                candidateReasons.push('text_keyword');
            }
            if (/btn|material|resource|assignment|lecture|lesson|download|file|list-group-item/i.test(className)) {
                candidateReasons.push('class_keyword');
            }

            return {
                index,
                href,
                text,
                class: className,
                is_candidate: candidateReasons.length > 0,
                candidate_reasons: candidateReasons
            };
        })"""
    )

    forms = page.locator("form").evaluate_all(
        """forms => forms.map((form, index) => ({
            index,
            action: form.action || form.getAttribute('action') || '',
            method: (form.getAttribute('method') || 'get').toLowerCase(),
            text_preview: (form.innerText || form.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 300)
        }))"""
    )

    try:
        body_text = page.locator("body").inner_text(timeout=1000)
    except PlaywrightError as exc:
        logging.warning("failed to read body text for lesson debug preview: %s", exc)
        body_text = ""

    iframe_counts = {
        "iframe": page.locator("iframe").count(),
        "iframe[src*='docs.google.com/presentation']": page.locator("iframe[src*='docs.google.com/presentation']").count(),
        "iframe[src*='docs.google.com/document']": page.locator("iframe[src*='docs.google.com/document']").count(),
        "iframe[src*='drive.google.com/file']": page.locator("iframe[src*='drive.google.com/file']").count(),
        "iframe[src*='viewer']": page.locator("iframe[src*='viewer']").count(),
    }

    return {
        "lesson_url": lesson_url,
        "page_url": page.url,
        "page_title": page.title(),
        "login_redirect_detected": "/signin" in urlparse(page.url).path or "/auth/" in urlparse(page.url).path,
        "fetched_at": utc_now_iso(),
        "iframe_counts": iframe_counts,
        "headings": headings,
        "iframes": iframes,
        "links": links,
        "forms": forms,
        "text_preview": normalize_space(body_text)[:1000],
    }


def extract_with_course_cards(page: Page, fetched_at: str) -> list[CourseProbeRecord]:
    records: list[CourseProbeRecord] = []
    cards = page.locator(COURSE_CARD_SELECTOR)
    count = cards.count()
    logging.info("selector=%r matched %s course cards", COURSE_CARD_SELECTOR, count)

    for index in range(count):
        card = cards.nth(index)
        media_body = card.locator(".media > .media-body, .media-body").first
        if media_body.count() == 0:
            logging.debug("skip course card without media body index=%s", index)
            continue

        try:
            title = normalize_space(media_body.locator(".media-heading").first.inner_text(timeout=1000))
        except PlaywrightError as exc:
            logging.debug("course title extraction failed index=%s error=%s", index, exc)
            title = ""

        if not title or title == "View Course":
            logging.debug("skip course card without usable title index=%s title=%r", index, title)
            continue

        course_link = media_body.locator("a.btn.btn-primary[href^='/courses/'], a[href^='/courses/']")
        href = ""
        absolute_url = ""
        for link_index in range(course_link.count()):
            candidate_href = course_link.nth(link_index).get_attribute("href") or ""
            candidate_url = urljoin(MOOCS_COURSES_URL, candidate_href)
            if is_course_url(candidate_url):
                href = candidate_href
                absolute_url = candidate_url
                break

            logging.debug("skip non-course href card_index=%s href=%r", index, candidate_href)

        if not href:
            logging.debug("skip course card without course link index=%s title=%r", index, title)
            continue

        records.append(
            CourseProbeRecord(
                course_title=title,
                course_url=absolute_url,
                retrieval_method=f"dom:{COURSE_CARD_SELECTOR}",
                fetched_at=fetched_at,
            )
        )

    return records


def extract_google_slides_materials(page: Page) -> list[CourseMaterialProbeRecord]:
    materials: list[CourseMaterialProbeRecord] = []
    iframes = page.locator(GOOGLE_SLIDES_IFRAME_SELECTOR)
    count = iframes.count()
    logging.info("selector=%r matched %s slides iframes", GOOGLE_SLIDES_IFRAME_SELECTOR, count)
    logging.info("found %s google_slides iframe", count)

    for index in range(count):
        iframe = iframes.nth(index)
        src = iframe.get_attribute("src") or ""
        slides_url = urljoin(page.url, src)
        if not slides_url:
            logging.debug("skip google slides iframe without src index=%s", index)
            continue

        materials.append(
            CourseMaterialProbeRecord(
                material_type="google_slides",
                material_url=slides_url,
                retrieval_method="iframe:google_slides",
            )
        )

    return materials


def path_segments(url: str) -> list[str]:
    return [segment for segment in urlparse(url).path.strip("/").split("/") if segment]


def fallback_title_from_url(url: str) -> str:
    segments = path_segments(url)
    return segments[-1] if segments else url


def extract_child_links(page: Page, parent_url: str, child_depth: int, link_kind: str) -> list[tuple[str, str]]:
    parent_path = urlparse(parent_url).path.rstrip("/")
    parent_segments = path_segments(parent_url)
    links = page.locator("a[href]")
    count = links.count()
    deduped: dict[str, tuple[str, int]] = {}
    logging.info("extracting %s links from %s anchors under %s", link_kind, count, parent_url)

    for index in range(count):
        link = links.nth(index)
        href = link.get_attribute("href") or ""
        absolute_url = urljoin(page.url, href).split("#", 1)[0].rstrip("/")
        parsed = urlparse(absolute_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc and parsed.netloc != urlparse(MOOCS_COURSES_URL).netloc:
            continue

        child_path = parsed.path.rstrip("/")
        child_segments = path_segments(absolute_url)
        if not child_path.startswith(parent_path + "/"):
            continue
        if len(child_segments) != len(parent_segments) + child_depth:
            continue

        title_score = 0
        try:
            title = clean_page_title_text(link.inner_text(timeout=1000))
        except PlaywrightError as exc:
            logging.debug("%s link title extraction failed index=%s href=%r error=%s", link_kind, index, href, exc)
            title = ""
        if is_usable_page_title(title):
            title_score = 2

        if title_score == 0:
            title = clean_page_title_text(link.get_attribute("aria-label") or "")
            if is_usable_page_title(title):
                title_score = 2
        if title_score == 0:
            title = clean_page_title_text(link.get_attribute("title") or "")
            if is_usable_page_title(title):
                title_score = 2
        if title_score == 0:
            title = fallback_title_from_url(absolute_url)
            title_score = 1

        existing = deduped.get(absolute_url)
        if existing is None or title_score > existing[1]:
            deduped[absolute_url] = (title, title_score)

    logging.info("extracted %s %s links", len(deduped), link_kind)
    return [(url, title) for url, (title, _score) in deduped.items()]


def validate_nonnegative_limit(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"--{name} must be 0 or greater")


def dedupe_courses(records: Iterable[CourseProbeRecord]) -> list[CourseProbeRecord]:
    deduped: dict[str, CourseProbeRecord] = {}
    for record in records:
        if record.course_url not in deduped:
            deduped[record.course_url] = record
    return list(deduped.values())


def log_dom_diagnostics(page: Page) -> None:
    try:
        body_text = page.locator("body").inner_text(timeout=1000)
    except PlaywrightError as exc:
        logging.warning("failed to read body text for diagnostics: %s", exc)
        body_text = ""

    logging.info("page title=%r url=%s", page.title(), page.url)
    logging.info("body text length=%s", len(body_text))

    for selector in VIEWER_FRAME_SELECTORS:
        count = page.locator(selector).count()
        logging.info("viewer selector=%r matched %s frames", selector, count)

    try:
        links = page.locator("a[href]").evaluate_all(
            """links => links.slice(0, 20).map(a => ({
                text: (a.innerText || a.getAttribute('aria-label') || '').trim(),
                href: a.href
            }))"""
        )
        logging.debug("first links=%s", links)
    except PlaywrightError as exc:
        logging.warning("failed to collect link diagnostics: %s", exc)


def probe_courses(
    storage_state: Path,
    profile_dir: Path | None,
    output_path: Path,
    headless: bool,
    timeout_ms: int,
) -> list[CourseProbeRecord]:
    fetched_at = utc_now_iso()

    with playwright_runner() as playwright:
        context = open_moocs_context(playwright, storage_state, profile_dir, headless)
        page = context.new_page()

        try:
            logging.info("opening %s", MOOCS_COURSES_URL)
            page.goto(MOOCS_COURSES_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                logging.warning("networkidle wait timed out; continuing with current DOM")
            wait_for_manual_login_if_needed(page, MOOCS_COURSES_URL, profile_dir, headless, timeout_ms)

            log_dom_diagnostics(page)

            courses = dedupe_courses(extract_with_course_cards(page, fetched_at))
            if not courses:
                log_dom_diagnostics(page)
                raise RuntimeError(
                    "MOOCs course extraction returned 0 records. "
                    "Likely causes: expired storage_state, login redirect, changed DOM, or selectors no longer matching."
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps([asdict(course) for course in courses], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logging.info("wrote %s courses to %s", len(courses), output_path)
        except PlaywrightTimeoutError:
            logging.warning("page load timed out; running diagnostics before failing")
            log_dom_diagnostics(page)
            raise
        finally:
            close_moocs_context(context)

    return courses


def probe_course_details(
    storage_state: Path,
    profile_dir: Path | None,
    courses_input_path: Path,
    output_path: Path,
    headless: bool,
    timeout_ms: int,
    details_limit: int | None,
    lesson_limit: int | None,
    page_limit: int | None,
    course_code: str | None = None,
) -> list[CourseDetailProbeRecord]:
    if not courses_input_path.exists():
        raise FileNotFoundError(
            f"courses input not found: {courses_input_path}. "
            "Run the course list probe first."
        )

    courses = load_course_records(courses_input_path)
    if not courses:
        raise RuntimeError(f"course input contained 0 valid records: {courses_input_path}")
    courses = filter_courses_by_code(courses, course_code)
    if not courses:
        raise RuntimeError(
            f"course input contained 0 records matching course_code={course_code!r}: {courses_input_path}"
        )
    validate_nonnegative_limit("details-limit", details_limit)
    validate_nonnegative_limit("lesson-limit", lesson_limit)
    validate_nonnegative_limit("page-limit", page_limit)
    if details_limit is not None:
        courses = courses[:details_limit]

    fetched_at = utc_now_iso()
    details: list[CourseDetailProbeRecord] = []

    with playwright_runner() as playwright:
        context = open_moocs_context(playwright, storage_state, profile_dir, headless)
        page = context.new_page()

        try:
            total_courses = len(courses)
            for course_index, course in enumerate(courses, start=1):
                logging.info("[course %s/%s] %s", course_index, total_courses, course.course_title)
                logging.info("opening course title=%r url=%s", course.course_title, course.course_url)
                try:
                    page.goto(course.course_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    except PlaywrightTimeoutError:
                        logging.warning("networkidle wait timed out for course=%s; continuing with current DOM", course.course_url)
                    wait_for_manual_login_if_needed(page, course.course_url, profile_dir, headless, timeout_ms)

                    log_dom_diagnostics(page)
                    if "/signin" in urlparse(page.url).path:
                        logging.warning(
                            "course redirected to signin; skipping course=%s. "
                            "Run with --user-data-dir %s --headed, complete MOOCs login, then retry.",
                            course.course_url,
                            DEFAULT_PROFILE_DIR,
                        )
                        continue

                    lessons: list[CourseLessonProbeRecord] = []
                    lesson_group_links = extract_child_links(
                        page=page,
                        parent_url=course.course_url,
                        child_depth=1,
                        link_kind="lesson_group",
                    )
                    total_lesson_groups = len(lesson_group_links)
                    if lesson_limit is not None:
                        lesson_group_links = lesson_group_links[:lesson_limit]
                        logging.info(
                            "lesson group traversal limited to %s of %s for course=%s",
                            len(lesson_group_links),
                            total_lesson_groups,
                            course.course_url,
                        )

                    for lesson_index, (lesson_url, lesson_title) in enumerate(lesson_group_links, start=1):
                        logging.info("[lesson %s/%s] %s", lesson_index, total_lesson_groups, lesson_title)
                        logging.info("opening lesson group title=%r url=%s", lesson_title, lesson_url)
                        try:
                            page.goto(lesson_url, wait_until="domcontentloaded", timeout=timeout_ms)
                            try:
                                page.wait_for_load_state("networkidle", timeout=timeout_ms)
                            except PlaywrightTimeoutError:
                                logging.warning("networkidle wait timed out for lesson=%s; continuing with current DOM", lesson_url)
                            wait_for_manual_login_if_needed(page, lesson_url, profile_dir, headless, timeout_ms)

                            log_dom_diagnostics(page)
                            if "/signin" in urlparse(page.url).path:
                                logging.warning(
                                    "lesson group redirected to signin; skipping lesson=%s. "
                                    "Persistent MOOCs login is missing or expired.",
                                    lesson_url,
                                )
                                continue

                            pages: list[CoursePageProbeRecord] = []
                            lesson_page_links = extract_child_links(
                                page=page,
                                parent_url=lesson_url,
                                child_depth=1,
                                link_kind="lesson_page",
                            )
                            total_lesson_pages = len(lesson_page_links)
                            if page_limit is not None:
                                lesson_page_links = lesson_page_links[:page_limit]
                                logging.info(
                                    "lesson page traversal limited to %s of %s for lesson=%s",
                                    len(lesson_page_links),
                                    total_lesson_pages,
                                    lesson_url,
                                )

                            for page_index, (lesson_page_url, lesson_page_link_title) in enumerate(lesson_page_links, start=1):
                                logging.info("[page %s/%s] %s", page_index, total_lesson_pages, lesson_page_url)
                                logging.info("opening lesson page title=%r url=%s", lesson_page_link_title, lesson_page_url)
                                try:
                                    page.goto(lesson_page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                                    try:
                                        page.wait_for_load_state("networkidle", timeout=timeout_ms)
                                    except PlaywrightTimeoutError:
                                        logging.warning(
                                            "networkidle wait timed out for lesson page=%s; continuing with current DOM",
                                            lesson_page_url,
                                        )
                                    wait_for_manual_login_if_needed(page, lesson_page_url, profile_dir, headless, timeout_ms)

                                    log_dom_diagnostics(page)
                                    if "/signin" in urlparse(page.url).path:
                                        logging.warning(
                                            "lesson page redirected to signin; recording redirect evidence for page=%s. "
                                            "Persistent MOOCs login is missing or expired.",
                                            lesson_page_url,
                                        )
                                        pages.append(
                                            CoursePageProbeRecord(
                                                page_title=lesson_page_link_title or fallback_title_from_url(lesson_page_url),
                                                page_url=lesson_page_url,
                                                materials=[],
                                                extracted_text=None,
                                                keyword_contexts=[],
                                                buttons=[],
                                                submit_button_present=False,
                                                deadline_text_candidates=[],
                                                accepting_status_text=None,
                                                non_google_iframe_urls=[],
                                                signin_redirect=True,
                                                content_fetched_at=fetched_at,
                                                content_retrieval_method="redirect:signin",
                                            )
                                        )
                                        continue

                                    materials = extract_google_slides_materials(page)
                                    evidence = extract_page_html_evidence(page, fetched_at)
                                    pages.append(
                                        CoursePageProbeRecord(
                                            page_title=extract_content_page_title(page, lesson_page_url),
                                            page_url=lesson_page_url,
                                            materials=materials,
                                            **evidence,
                                        )
                                    )
                                except PlaywrightTimeoutError:
                                    logging.warning("lesson page load timed out; skipping page=%s", lesson_page_url)
                                    log_dom_diagnostics(page)
                                    continue
                                except PlaywrightError as exc:
                                    logging.warning("lesson page probe failed; skipping page=%s error=%s", lesson_page_url, exc)
                                    log_dom_diagnostics(page)
                                    continue

                            lessons.append(
                                CourseLessonProbeRecord(
                                    lesson_title=lesson_title,
                                    lesson_url=lesson_url,
                                    pages=pages,
                                )
                            )
                        except PlaywrightTimeoutError:
                            logging.warning("lesson group load timed out; skipping lesson=%s", lesson_url)
                            log_dom_diagnostics(page)
                            continue
                        except PlaywrightError as exc:
                            logging.warning("lesson group probe failed; skipping lesson=%s error=%s", lesson_url, exc)
                            log_dom_diagnostics(page)
                            continue

                    details.append(
                        CourseDetailProbeRecord(
                            course_title=course.course_title,
                            course_url=course.course_url,
                            lessons=lessons,
                            fetched_at=fetched_at,
                        )
                    )
                except PlaywrightTimeoutError:
                    logging.warning("course load timed out; skipping course=%s", course.course_url)
                    log_dom_diagnostics(page)
                    continue
                except PlaywrightError as exc:
                    logging.warning("course probe failed; skipping course=%s error=%s", course.course_url, exc)
                    log_dom_diagnostics(page)
                    continue
        finally:
            close_moocs_context(context)

    if not details and output_path.exists():
        logging.warning(
            "course detail probe returned 0 records; keeping existing output file=%s",
            output_path,
        )
        return details

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([course_detail_to_dict(detail) for detail in details], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logging.info("wrote %s course detail records to %s", len(details), output_path)

    return details


def probe_course_links_debug(
    storage_state: Path,
    profile_dir: Path | None,
    course_url: str,
    output_path: Path,
    headless: bool,
    timeout_ms: int,
) -> dict[str, object]:
    with playwright_runner() as playwright:
        context = open_moocs_context(playwright, storage_state, profile_dir, headless)
        page = context.new_page()

        try:
            logging.info("opening course debug url=%s", course_url)
            page.goto(course_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                logging.warning("networkidle wait timed out; continuing with current DOM")
            wait_for_manual_login_if_needed(page, course_url, profile_dir, headless, timeout_ms)

            log_dom_diagnostics(page)
            debug_payload = collect_course_link_debug(page, course_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(debug_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logging.info(
                "wrote %s links to %s",
                len(debug_payload.get("links", [])),
                output_path,
            )
        except PlaywrightTimeoutError:
            logging.warning("page load timed out; running diagnostics before failing")
            log_dom_diagnostics(page)
            raise
        finally:
            close_moocs_context(context)

    return debug_payload


def probe_lesson_debug(
    storage_state: Path,
    profile_dir: Path | None,
    lesson_url: str,
    output_path: Path,
    headless: bool,
    timeout_ms: int,
) -> dict[str, object]:
    with playwright_runner() as playwright:
        context = open_moocs_context(playwright, storage_state, profile_dir, headless)
        page = context.new_page()

        try:
            logging.info("opening lesson debug url=%s", lesson_url)
            page.goto(lesson_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                logging.warning("networkidle wait timed out; continuing with current DOM")
            wait_for_manual_login_if_needed(page, lesson_url, profile_dir, headless, timeout_ms)

            log_dom_diagnostics(page)
            debug_payload = collect_lesson_debug(page, lesson_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(debug_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logging.info(
                "wrote lesson debug with %s links and %s iframes to %s",
                len(debug_payload.get("links", [])),
                len(debug_payload.get("iframes", [])),
                output_path,
            )
        except PlaywrightTimeoutError:
            logging.warning("page load timed out; running diagnostics before failing")
            log_dom_diagnostics(page)
            raise
        finally:
            close_moocs_context(context)

    return debug_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe MOOCs course list from logged-in DOM.")
    parser.add_argument("--storage-state", type=Path, default=DEFAULT_STORAGE_STATE)
    parser.add_argument(
        "--user-data-dir",
        type=Path,
        default=None,
        help=(
            "Use a persistent Chromium user data directory instead of storage_state. "
            f"Recommended for MOOCs login state, e.g. {DEFAULT_PROFILE_DIR}."
        ),
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=None,
        help="Deprecated alias for --user-data-dir.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--details", action="store_true", help="Probe each course detail page from moocs_courses.json.")
    parser.add_argument("--courses-input", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--details-output", type=Path, default=DEFAULT_DETAILS_OUTPUT_PATH)
    parser.add_argument("--course-code", help="Limit --details traversal to one course code, e.g. COT101.")
    parser.add_argument("--details-limit", type=int, default=None, help="Limit the number of courses visited by --details.")
    parser.add_argument("--lesson-limit", type=int, default=None, help="Limit lesson groups visited per course by --details.")
    parser.add_argument("--page-limit", type=int, default=None, help="Limit lesson pages visited per lesson group by --details.")
    parser.add_argument("--links-debug", action="store_true", help="Write link diagnostics for one course detail page.")
    parser.add_argument("--links-debug-course-url", default=DEFAULT_LINKS_DEBUG_COURSE_URL)
    parser.add_argument("--links-debug-output", type=Path, default=DEFAULT_LINKS_DEBUG_OUTPUT_PATH)
    parser.add_argument("--lesson-debug", help="Write diagnostics for one MOOCs lesson/material page URL.")
    parser.add_argument("--lesson-debug-output", type=Path, default=DEFAULT_LESSON_DEBUG_OUTPUT_PATH)
    parser.add_argument(
        "--save-storage-state",
        action="store_true",
        help=(
            "Open MOOCs with a persistent profile, verify a content page, then save "
            "storage_state for headless HTTP/Playwright imports."
        ),
    )
    parser.add_argument(
        "--check-url",
        nargs="?",
        const=DEFAULT_CONTENT_CHECK_URL,
        default=None,
        help=(
            "Verify logged-in access to a MOOCs URL. If no URL is supplied, checks "
            f"{DEFAULT_CONTENT_CHECK_URL}."
        ),
    )
    parser.add_argument("--headed", action="store_true", help="Run Chromium with a visible browser window.")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--login-wait-ms",
        type=int,
        default=300000,
        help="When --save-storage-state is headed, wait this long for manual login before refusing to save.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)
    user_data_dir = args.user_data_dir or args.profile_dir

    if args.save_storage_state:
        profile_dir = user_data_dir or DEFAULT_PROFILE_DIR
        result = save_storage_state_from_profile(
            storage_state=args.storage_state,
            profile_dir=profile_dir,
            check_url=args.check_url or DEFAULT_CONTENT_CHECK_URL,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
            login_wait_ms=args.login_wait_ms,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.check_url:
        result = check_moocs_url_access(
            storage_state=args.storage_state,
            profile_dir=user_data_dir,
            url=args.check_url,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.lesson_debug:
        probe_lesson_debug(
            storage_state=args.storage_state,
            profile_dir=user_data_dir,
            lesson_url=args.lesson_debug,
            output_path=args.lesson_debug_output,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
        )
        return

    if args.links_debug:
        probe_course_links_debug(
            storage_state=args.storage_state,
            profile_dir=user_data_dir,
            course_url=args.links_debug_course_url,
            output_path=args.links_debug_output,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
        )
        return

    if args.details:
        probe_course_details(
            storage_state=args.storage_state,
            profile_dir=user_data_dir,
            courses_input_path=args.courses_input,
            output_path=args.details_output,
            headless=not args.headed,
            timeout_ms=args.timeout_ms,
            details_limit=args.details_limit,
            lesson_limit=args.lesson_limit,
            page_limit=args.page_limit,
            course_code=args.course_code,
        )
        return

    probe_courses(
        storage_state=args.storage_state,
        profile_dir=user_data_dir,
        output_path=args.output,
        headless=not args.headed,
        timeout_ms=args.timeout_ms,
    )


if __name__ == "__main__":
    main()
