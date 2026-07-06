from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import asdict
import json
import os
import sys
import time
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from bs4 import BeautifulSoup
import meilisearch
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
import psycopg
import requests
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_module import generate_answer
from backend.app.core.context_cards import build_local_resource_card
from backend.app.core.context_pack import MATERIAL_SEARCH_CAUTION
from backend.app.core.course_rules import normalize_course_code
from backend.app.core.embeddings import (
    HashedBagOfWordsEmbeddingProvider,
    cosine_similarity,
)
from backend.app.core.material_chunks import chunk_material_texts
from backend.app.core.material_search import (
    load_material_chunk_index,
    load_material_text_index,
    normalize_mode as normalize_material_search_mode,
    search_context_pack,
    search_material_chunks,
)
from backend.app.core.material_text import material_texts_from_local_resources
from backend.app.core.ontology import (
    ENTITY_TYPE_RESOURCE,
    infer_resource_kind,
    normalize_resource_kind,
    normalize_source_kind,
)
from backend.app.core.task_backlog import (
    build_pending_tasks_payload,
    summarize_task_backlog_payload,
)
from backend.app.core.task_html_evidence import load_html_evidence_by_course
from backend.app.core.task_slides_evidence import load_slides_evidence_by_course
from backend.app.core.task_generator import generate_course_rule_tasks
from backend.app.core.task_list_composer import compose_task_list_items
from backend.app.core.user_task_status import (
    ALLOWED_USER_TASK_STATUSES,
    UserTaskStatus,
    create_default_status,
    mark_done,
    mark_ignored,
    mark_todo,
)
from backend.app.core.user_task_status_store import (
    load_user_task_statuses,
    save_user_task_statuses,
)
from database import init_db

app = FastAPI()
init_db()
USER_TASK_STATUSES: dict[str, UserTaskStatus] = {}
USER_TASK_STATUS_WARNINGS: list[dict[str, str]] = []
USER_TASK_STATUS_LOADED = False
USER_TASK_STATUS_PATH = PROJECT_ROOT / "data" / "local" / "user_task_status.json"
HTML_EVIDENCE_PATH = PROJECT_ROOT / "data" / "probe" / "moocs_course_details.json"
LOCAL_RESOURCE_INDEX_PATH = PROJECT_ROOT / "data" / "local" / "resource_index.json"
MATERIAL_TEXT_INDEX_PATH = PROJECT_ROOT / "data" / "local" / "material_text_index.json"
MATERIAL_CHUNK_INDEX_PATH = PROJECT_ROOT / "data" / "local" / "material_chunk_index.json"
LOCAL_RESOURCE_SEARCH_MODES = frozenset({"keyword", "semantic", "hybrid"})
LOCAL_EMBEDDING_PROVIDER = HashedBagOfWordsEmbeddingProvider()
MOOCS_COLLECT_DB_PATH = (
    Path(os.environ["MOOCS_COLLECT_DB_PATH"]).expanduser()
    if os.environ.get("MOOCS_COLLECT_DB_PATH")
    else None
)

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")
COURSE_DETAILS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "probe" / "moocs_course_details.json"
)
DEFAULT_MOOCS_STORAGE_STATE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "probe" / "moocs_storage_state.json"
)
DEFAULT_MEILI_URL = "http://meilisearch:7700"
DEFAULT_MEILI_MASTER_KEY = "dev-master-key"
DEFAULT_MEILI_INDEX = "search_documents"
DEFAULT_ASK_TIMEOUT_SECONDS = 20
MEILI_SEARCHABLE_ATTRIBUTES = [
    "course_code",
    "title",
    "lecture_title",
    "course_title",
    "content_excerpt",
    "snippet",
    "search_text",
    "source_url",
]
MEILI_FILTERABLE_ATTRIBUTES = [
    "type",
    "course_code",
    "course_id",
    "lecture_id",
]
MEILI_SORTABLE_ATTRIBUTES = [
    "lecture_number",
    "db_id",
]
CONTENT_TEXT_KEYS = {
    "content",
    "text",
    "body",
    "description",
    "transcript",
    "extracted_text",
    "raw",
}
CONTENT_EXCERPT_LIMIT = 1000
HTML_EXTRACTED_TEXT_LIMIT = 8000
HTML_FETCH_TIMEOUT_SECONDS = 12


def utf8_json(data):
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
    )


class AskRequest(BaseModel):
    question: str


class TaskStatusUpdateRequest(BaseModel):
    status: str


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None, {
            "status": "error",
            "detail": "DATABASE_URL is not set",
        }
    return database_url, None


def extract_course_code(course):
    course_code = str(course.get("course_code", "")).strip()
    if course_code:
        return course_code

    course_url = str(course.get("course_url", "")).strip()
    path = urlparse(course_url).path.rstrip("/")
    if not path:
        return ""
    return path.rsplit("/", 1)[-1].strip()


def extract_course_title(course):
    for key in ("course_title", "title"):
        title = str(course.get(key, "")).strip()
        if title:
            return title
    return ""


def extract_lecture_items(course):
    lessons = course.get("lessons")
    if not isinstance(lessons, list):
        return []

    lecture_items = []
    for index, lesson in enumerate(lessons, start=1):
        if not isinstance(lesson, dict):
            continue

        title = str(lesson.get("lesson_title", "")).strip()
        if not title:
            continue

        lecture_items.append(
            {
                "lecture_number": index,
                "title": title,
            }
        )

    return lecture_items


def extract_page_items(course):
    lessons = course.get("lessons")
    if not isinstance(lessons, list):
        return []

    page_items = []
    for lecture_number, lesson in enumerate(lessons, start=1):
        if not isinstance(lesson, dict):
            continue

        lecture_title = str(lesson.get("lesson_title", "")).strip()
        pages = lesson.get("pages")
        if not isinstance(pages, list):
            continue

        for page_number, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue

            title = str(page.get("page_title", "")).strip()
            url = str(page.get("page_url", "")).strip()
            if not title and not url:
                continue

            page_items.append(
                {
                    "lecture_number": lecture_number,
                    "lecture_title": lecture_title,
                    "page_number": page_number,
                    "title": title,
                    "url": url,
                    "raw_json": page,
                }
            )

    return page_items


def extract_material_items(course):
    page_items = extract_page_items(course)
    material_items = []

    for page in page_items:
        materials = page["raw_json"].get("materials")
        if not isinstance(materials, list):
            continue

        for material_number, material in enumerate(materials, start=1):
            if not isinstance(material, dict):
                continue

            material_type = str(material.get("material_type", "")).strip()
            url = str(material.get("material_url", "")).strip()
            retrieval_method = str(material.get("retrieval_method", "")).strip()
            if not material_type and not url and not retrieval_method:
                continue

            material_items.append(
                {
                    "lecture_number": page["lecture_number"],
                    "lecture_title": page["lecture_title"],
                    "page_number": page["page_number"],
                    "page_title": page["title"],
                    "page_url": page["url"],
                    "material_number": material_number,
                    "material_type": material_type,
                    "url": url,
                    "retrieval_method": retrieval_method,
                    "raw_json": material,
                }
            )

    return material_items


TASK_KEYWORDS = (
    "課題",
    "提出",
    "締切",
    "exercise",
    "assignment",
    "homework",
)

TASK_DUE_KEYS = (
    "due",
    "due_date",
    "deadline",
    "deadline_at",
    "due_at",
)


def contains_task_keyword(*values):
    haystack = " ".join(str(value) for value in values if value).lower()
    return any(keyword.lower() in haystack for keyword in TASK_KEYWORDS)


def looks_like_task_query(query):
    task_search_words = {
        "課題",
        "宿題",
        "提出",
        "締切",
        "レポート",
        "task",
        "tasks",
        "assignment",
        "assignments",
        "homework",
        "deadline",
        "deadlines",
        "exercise",
        "exercises",
    }
    lowered = query.lower()
    return any(word in lowered for word in task_search_words)


def looks_like_content_query(query):
    content_words = (
        "内容",
        "学ぶ",
        "何をする",
        "どんな講義",
        "変数",
        "python",
        "システムガイダンス",
    )
    lowered = query.lower()
    return any(word in lowered for word in content_words)


def looks_like_course_overview_query(query):
    normalized = normalize_search_text(query)
    overview_phrases = (
        "cot101とは",
        "cot101 とは",
        "cot101では何を学ぶ",
        "cot101 では何を学ぶ",
        "cs概論とは",
        "cs概論 とは",
        "コンピュータ・サイエンス概論とは",
    )
    return any(phrase in normalized for phrase in overview_phrases)


def search_query_intent(query):
    if looks_like_course_overview_query(query):
        return "course_overview"
    if looks_like_task_query(query):
        return "task"
    if looks_like_content_query(query):
        return "content"
    return "general"


def looks_like_recent_task_query(query):
    recent_words = ("一番新しい", "最新", "新しい")
    return any(word in query for word in recent_words)


def normalize_search_text(value):
    return (
        str(value or "")
        .lower()
        .replace("　", " ")
        .replace("１", "1")
        .replace("Ⅰ", "i")
        .replace("ⅰ", "i")
    )


def specific_query_text(query):
    normalized = normalize_search_text(query)
    remove_words = (
        "一番新しい",
        "最新",
        "新しい",
        "最近",
        "今週",
        "課題",
        "宿題",
        "提出",
        "締切",
        "レポート",
        "assignment",
        "assignments",
        "homework",
        "deadline",
        "deadlines",
        "exercise",
        "exercises",
        "task",
        "tasks",
        "教えて",
        "ください",
        "一覧",
        "の",
        "を",
        "は",
        "について",
        "cot101",
    )
    for word in remove_words:
        normalized = normalized.replace(word, " ")
    return " ".join(normalized.split())


def meili_query_text(query):
    normalized = normalize_search_text(query)
    remove_words = (
        "一番新しい",
        "最新",
        "新しい",
        "最近",
        "今週",
        "教えて",
        "ください",
        "一覧",
        "について",
        "とは",
        "では",
        "何を学ぶ",
        "の",
        "を",
        "は",
    )
    for word in remove_words:
        normalized = normalized.replace(word, " ")
    return " ".join(normalized.split()) or query


def item_matches_specific_query(item, specific_text):
    if not specific_text:
        return True

    haystack = normalize_search_text(
        " ".join(
            str(item.get(key) or "")
            for key in ("title", "lecture_title", "course_title", "source_url")
        )
    )
    return all(part in haystack for part in specific_text.split())


def course_code_matches_query(item, query):
    course_code = normalize_search_text(item.get("course_code"))
    if not course_code:
        return True
    return course_code in normalize_search_text(query)


def course_code_penalty(item, query):
    normalized_query = normalize_search_text(query)
    course_code = normalize_search_text(item.get("course_code"))
    if not course_code or not any(char.isdigit() for char in normalized_query):
        return 0
    return 0 if course_code in normalized_query else 1


def meili_task_filter(query):
    normalized_query = normalize_search_text(query)
    if "cot101" in normalized_query:
        return 'type = task AND course_code = "COT101"'
    return "type = task"


def meili_course_filter(query):
    normalized_query = normalize_search_text(query)
    if "cot101" in normalized_query or "cs概論" in normalized_query:
        return 'course_code = "COT101"'
    return ""


def json_text(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else ""


def compact_text(value):
    return " ".join(str(value or "").split())


def truncate_text(value, limit=CONTENT_EXCERPT_LIMIT):
    text = compact_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def collect_text_fields(value):
    texts = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in CONTENT_TEXT_KEYS and isinstance(item, (str, int, float)):
                text = compact_text(item)
                if text:
                    texts.append(text)
            elif isinstance(item, (dict, list)):
                texts.extend(collect_text_fields(item))
    elif isinstance(value, list):
        for item in value:
            texts.extend(collect_text_fields(item))
    return texts


def content_excerpt_from_raw_json(raw_json, limit=CONTENT_EXCERPT_LIMIT):
    if isinstance(raw_json, str):
        try:
            raw_json = json.loads(raw_json)
        except json.JSONDecodeError:
            return truncate_text(raw_json, limit)

    return truncate_text(" ".join(collect_text_fields(raw_json)), limit)


def extract_text_from_html(html, limit=HTML_EXTRACTED_TEXT_LIMIT):
    soup = BeautifulSoup(html or "", "html.parser")
    for selector in (
        "script",
        "style",
        "noscript",
        "nav",
        "header",
        "footer",
        "aside",
        "iframe",
        "form",
        ".navbar",
        ".sidebar",
        ".main-header",
        ".main-sidebar",
        ".content-header",
        ".breadcrumb",
        ".control-sidebar",
        ".bookmark",
        ".pagination",
        ".pager",
    ):
        for element in soup.select(selector):
            element.decompose()

    candidates = []
    for selector in (
        ".content-wrapper section.content",
        "section.content",
        ".content-wrapper",
        "main",
        "article",
        "body",
    ):
        for element in soup.select(selector):
            text = clean_extracted_html_text(element.get_text(separator=" ", strip=True))
            if text:
                candidates.append(text)

    text = max(candidates, key=len, default="")
    return truncate_text(text, limit)


def clean_extracted_html_text(value):
    text = compact_text(value)
    noise_phrases = (
        "Bookmark",
        "« Previous Next »",
        "Previous Next",
        "« Previous",
        "Next »",
    )
    for phrase in noise_phrases:
        text = text.replace(phrase, " ")
    return compact_text(text)


def looks_like_moocs_login_page(html, text):
    haystack = normalize_search_text(f"{html or ''} {text or ''}")
    login_markers = (
        "sign in with iniad account",
        "/signin",
        "welcome to iniad moocs educational platform",
    )
    content_markers = (
        "content-wrapper",
        "section class=\"content",
        "section content",
    )
    return any(marker in haystack for marker in login_markers) and not any(
        marker in haystack for marker in content_markers
    )


def moocs_storage_state_path():
    raw_path = os.getenv("MOOCS_STORAGE_STATE")
    if raw_path:
        return Path(raw_path)
    return DEFAULT_MOOCS_STORAGE_STATE_PATH


def moocs_user_data_dir_path():
    raw_path = os.getenv("MOOCS_USER_DATA_DIR")
    if raw_path:
        return Path(raw_path)
    return None


def moocs_playwright_headless():
    # MOOCs invalidates or rejects authenticated sessions when Chromium is headless.
    # Keep the content fallback headed even if MOOCS_PLAYWRIGHT_HEADLESS is set.
    return False


def load_moocs_storage_cookies(session):
    storage_state_path = moocs_storage_state_path()
    if not storage_state_path.exists():
        return

    try:
        storage_state = json.loads(storage_state_path.read_text(encoding="utf-8"))
    except Exception:
        return

    for cookie in storage_state.get("cookies", []):
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        session.cookies.set(
            name,
            value,
            domain=cookie.get("domain"),
            path=cookie.get("path") or "/",
            secure=bool(cookie.get("secure", False)),
        )


def build_moocs_http_session():
    session = requests.Session()
    load_moocs_storage_cookies(session)
    return session


class MoocsHtmlTextExtractor:
    def __init__(self):
        self.session = build_moocs_http_session()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def close(self):
        for resource in (self.context, self.browser, self.playwright):
            if resource is None:
                continue
            try:
                if hasattr(resource, "stop"):
                    resource.stop()
                else:
                    resource.close()
            except Exception:
                pass

    def extract(self, url):
        text = fetch_html_extracted_text(url, session=self.session)
        if text:
            return text
        return self.extract_with_playwright(url)

    def ensure_playwright_page(self):
        if self.page is not None:
            return self.page

        user_data_dir_path = moocs_user_data_dir_path()
        if user_data_dir_path is None:
            return None

        self.playwright = sync_playwright().start()
        user_data_dir_path.mkdir(parents=True, exist_ok=True)
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir_path),
            headless=moocs_playwright_headless(),
        )
        self.page = self.context.new_page()
        return self.page

    def extract_with_playwright(self, url):
        page = self.ensure_playwright_page()
        if page is None:
            return ""

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=HTML_FETCH_TIMEOUT_SECONDS * 1000,
            )
            if "/signin" in urlparse(page.url).path:
                return ""
            html = page.content()
        except (PlaywrightTimeoutError, Exception):
            return ""

        extracted_text = extract_text_from_html(html)
        if looks_like_moocs_login_page(html, extracted_text):
            return ""
        return extracted_text


def fetch_html_extracted_text(url, session=None):
    if not url:
        return ""

    http = session or requests
    response = http.get(
        url,
        timeout=HTML_FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": "INIAD-AIO/0.2.5 content-rag-poc"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        return ""

    extracted_text = extract_text_from_html(response.text)
    if looks_like_moocs_login_page(response.text, extracted_text):
        return ""
    return extracted_text


def page_raw_json_with_extracted_text(raw_json, url, session=None, extractor=None):
    if not isinstance(raw_json, dict):
        return raw_json

    enriched = dict(raw_json)
    try:
        if extractor is not None:
            extracted_text = extractor.extract(url)
        else:
            extracted_text = fetch_html_extracted_text(url, session=session)
    except Exception:
        return enriched

    if extracted_text:
        enriched["extracted_text"] = extracted_text
    return enriched


def find_first_value_by_keys(value, keys):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and item:
                return item
            found = find_first_value_by_keys(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_first_value_by_keys(item, keys)
            if found:
                return found
    return None


def normalize_due_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def extract_task_items(course):
    page_items = extract_page_items(course)
    task_items = []

    for page in page_items:
        raw_page = page["raw_json"]
        page_due = find_first_value_by_keys(raw_page, TASK_DUE_KEYS)
        page_is_task = contains_task_keyword(
            page["title"],
            page["url"],
            raw_page.get("type"),
            raw_page.get("body"),
            raw_page.get("description"),
            json_text(raw_page),
        )

        if page_is_task or page_due:
            task_items.append(
                {
                    "lecture_number": page["lecture_number"],
                    "lecture_title": page["lecture_title"],
                    "title": page["title"] or page["url"],
                    "due_date": page_due,
                    "source_type": "page",
                    "source_url": page["url"],
                    "raw_json": raw_page,
                }
            )

        materials = raw_page.get("materials")
        if not isinstance(materials, list):
            continue

        for material in materials:
            if not isinstance(material, dict):
                continue

            material_title = str(
                material.get("material_title")
                or material.get("title")
                or material.get("name")
                or ""
            ).strip()
            material_url = str(material.get("material_url", "")).strip()
            material_type = str(material.get("material_type", "")).strip()
            retrieval_method = str(material.get("retrieval_method", "")).strip()
            material_due = find_first_value_by_keys(material, TASK_DUE_KEYS)
            material_is_task = contains_task_keyword(
                material_title,
                material_url,
                material_type,
                retrieval_method,
                material.get("type"),
                material.get("body"),
                material.get("description"),
                json_text(material),
            )

            if not material_is_task and not material_due:
                continue

            task_items.append(
                {
                    "lecture_number": page["lecture_number"],
                    "lecture_title": page["lecture_title"],
                    "title": material_title or page["title"] or material_url,
                    "due_date": material_due,
                    "source_type": "material",
                    "source_url": material_url,
                    "raw_json": material,
                }
            )

    return task_items


def ask_timeout_seconds():
    raw_value = os.getenv("ASK_TIMEOUT_SECONDS", str(DEFAULT_ASK_TIMEOUT_SECONDS))
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_ASK_TIMEOUT_SECONDS


def generate_answer_with_timeout(question, sources):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(generate_answer, question, sources)
    try:
        return future.result(timeout=ask_timeout_seconds())
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def source_type_label(source_type):
    labels = {
        "task": "課題",
        "lecture": "講義",
        "page": "ページ",
        "course": "コース",
        "material": "資料",
    }
    return labels.get(source_type, source_type or "情報")


def sorted_fallback_sources(question, sources):
    indexed_sources = list(enumerate(sources or []))
    if not looks_like_task_query(question):
        return [source for _, source in indexed_sources]

    recent_query = looks_like_recent_task_query(question)

    def fallback_rank(indexed_source):
        original_index, source = indexed_source
        lecture_number = source.get("lecture_number") or -1
        type_order = {
            "task": 0,
            "page": 1,
            "lecture": 2,
            "course": 3,
        }
        if recent_query:
            return (
                type_order.get(source.get("type"), 9),
                -lecture_number,
                original_index,
            )
        return (
            type_order.get(source.get("type"), 9),
            original_index,
            -lecture_number,
        )

    return [
        source
        for _, source in sorted(
            indexed_sources,
            key=fallback_rank,
        )
    ]


def format_fallback_source(source):
    label = source_type_label(source.get("type"))
    course_code = source.get("course_code") or "course未設定"
    lecture_number = source.get("lecture_number")
    lecture_part = str(lecture_number) if lecture_number is not None else "lecture未設定"
    title = source.get("title") or source.get("lecture_title") or "タイトル未設定"
    source_url = source.get("source_url") or "URLなし"
    return f"- [{label}] {course_code} / {lecture_part} / {title} / {source_url}"


def build_fallback_answer(question, sources, reason=None):
    fallback_sources = sorted_fallback_sources(question, sources)[:8]
    lines = [
        "AI回答生成に失敗したため、検索結果をもとに関連情報を表示します。",
    ]
    if reason:
        lines.append(f"理由: {reason}")
    lines.append("")

    if not fallback_sources:
        lines.append("検索結果は見つかりませんでした。")
        return "\n".join(lines)

    lines.extend(format_fallback_source(source) for source in fallback_sources)
    return "\n".join(lines)


@app.post("/api/ask")
def ask(request: AskRequest):
    question = request.question.strip()

    if not question:
        return utf8_json({
            "answer": "",
            "sources": [],
            "error": "質問を入力してください。",
        })

    sources = []

    try:
        search_response = search_database_data(question, limit=12)
    except Exception as exc:
        return utf8_json({
            "answer": "",
            "sources": sources,
            "error": str(exc),
        })

    if search_response.get("status") != "ok":
        return utf8_json({
            "answer": "",
            "sources": [],
            "error": search_response.get("detail", "search failed"),
        })

    sources = search_response.get("results", [])

    try:
        answer = generate_answer_with_timeout(question, sources)
        if not answer or not answer.strip():
            answer = build_fallback_answer(question, sources, "AIモデルが空の回答を返しました。")
            return utf8_json({
                "answer": answer,
                "sources": sources,
                "error": "empty AI answer",
            })
    except TimeoutError:
        return utf8_json({
            "answer": build_fallback_answer(
                question,
                sources,
                f"AI回答生成が {ask_timeout_seconds()} 秒以内に完了しませんでした。",
            ),
            "sources": sources,
            "error": "AI answer generation timed out",
        })
    except Exception as exc:
        return utf8_json({
            "answer": build_fallback_answer(question, sources, str(exc)),
            "sources": sources,
            "error": str(exc),
        })

    return utf8_json({
        "answer": answer,
        "sources": sources,
    })


@app.get("/api/db-test")
def db_test():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                postgresql = cur.fetchone()[0]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "postgresql": postgresql,
    }


@app.get("/api/init-db")
def init_postgresql_db():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "message": "database initialized",
    }


@app.get("/api/db-status")
def db_status():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tablename "
                    "FROM pg_tables "
                    "WHERE schemaname='public';"
                )
                tables = [row[0] for row in cur.fetchall()]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "tables": tables,
    }


@app.get("/api/import-courses")
def import_courses():
    database_url, error = get_database_url()
    if error:
        return error

    if not COURSE_DETAILS_PATH.exists():
        return {
            "status": "error",
            "detail": "moocs_course_details.json not found",
        }

    try:
        raw_courses = json.loads(COURSE_DETAILS_PATH.read_text(encoding="utf-8"))
        imported = 0
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for course in raw_courses:
                    if not isinstance(course, dict):
                        continue

                    course_code = extract_course_code(course)
                    title = extract_course_title(course)
                    if not course_code or not title:
                        continue

                    cur.execute(
                        """
                        INSERT INTO courses (course_code, title)
                        VALUES (%s, %s)
                        ON CONFLICT (course_code)
                        DO UPDATE SET title = EXCLUDED.title;
                        """,
                        (course_code, title),
                    )
                    imported += 1
            conn.commit()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "imported": imported,
    }


@app.get("/api/import-lectures")
def import_lectures():
    database_url, error = get_database_url()
    if error:
        return error

    if not COURSE_DETAILS_PATH.exists():
        return {
            "status": "error",
            "detail": "moocs_course_details.json not found",
        }

    try:
        raw_courses = json.loads(COURSE_DETAILS_PATH.read_text(encoding="utf-8"))
        imported = 0
        found_lecture_metadata = False

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for course in raw_courses:
                    if not isinstance(course, dict):
                        continue

                    course_code = extract_course_code(course)
                    if not course_code:
                        continue

                    lecture_items = extract_lecture_items(course)
                    if not lecture_items:
                        continue

                    found_lecture_metadata = True

                    cur.execute(
                        "SELECT id FROM courses WHERE course_code = %s;",
                        (course_code,),
                    )
                    row = cur.fetchone()
                    if not row:
                        continue

                    course_id = row[0]

                    for lecture in lecture_items:
                        lecture_number = lecture["lecture_number"]
                        title = lecture["title"]

                        cur.execute(
                            """
                            SELECT id
                            FROM lectures
                            WHERE course_id = %s
                              AND (
                                lecture_number = %s
                                OR title = %s
                              )
                            LIMIT 1;
                            """,
                            (course_id, lecture_number, title),
                        )
                        if cur.fetchone():
                            continue

                        cur.execute(
                            """
                            INSERT INTO lectures (course_id, lecture_number, title)
                            VALUES (%s, %s, %s);
                            """,
                            (course_id, lecture_number, title),
                        )
                        imported += 1
            conn.commit()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    if not found_lecture_metadata:
        return {
            "status": "ok",
            "imported": 0,
            "message": "lecture metadata not found in moocs_course_details.json",
        }

    return {
        "status": "ok",
        "imported": imported,
    }


@app.post("/api/import-pages")
def import_pages(
    course_code: str | None = Query(default=None),
    page_limit: int | None = Query(default=None, ge=0),
    dry_run: bool = Query(default=False),
):
    database_url, error = get_database_url()
    if error:
        return error

    if not isinstance(course_code, str):
        course_code = None
    if not isinstance(page_limit, int):
        page_limit = None
    if not isinstance(dry_run, bool):
        dry_run = False

    requested_course_code = (course_code or "").strip()
    if not requested_course_code and not dry_run:
        return {
            "status": "error",
            "detail": "course_code is required for /api/import-pages unless dry_run=true",
        }

    if not COURSE_DETAILS_PATH.exists():
        return {
            "status": "error",
            "detail": "moocs_course_details.json not found",
        }

    try:
        raw_courses = json.loads(COURSE_DETAILS_PATH.read_text(encoding="utf-8"))
        imported = 0
        updated = 0
        planned = 0
        skipped_missing_lecture = 0
        found_page_metadata = False

        html_extractor = None if dry_run else MoocsHtmlTextExtractor()
        try:
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    for course in raw_courses:
                        if not isinstance(course, dict):
                            continue

                        course_code = extract_course_code(course)
                        if not course_code:
                            continue
                        if requested_course_code and course_code.lower() != requested_course_code.lower():
                            continue

                        page_items = extract_page_items(course)
                        if not page_items:
                            continue
                        if page_limit is not None:
                            page_items = page_items[:page_limit]

                        found_page_metadata = True

                        cur.execute(
                            "SELECT id FROM courses WHERE course_code = %s;",
                            (course_code,),
                        )
                        course_row = cur.fetchone()
                        if not course_row:
                            continue

                        course_id = course_row[0]

                        for page in page_items:
                            cur.execute(
                                """
                                SELECT id
                                FROM lectures
                                WHERE course_id = %s
                                  AND (
                                    lecture_number = %s
                                    OR title = %s
                                  )
                                LIMIT 1;
                                """,
                                (
                                    course_id,
                                    page["lecture_number"],
                                    page["lecture_title"],
                                ),
                            )
                            lecture_row = cur.fetchone()
                            if not lecture_row:
                                skipped_missing_lecture += 1
                                continue

                            lecture_id = lecture_row[0]
                            planned += 1
                            if dry_run:
                                continue

                            time.sleep(1)
                            page_raw_json = page_raw_json_with_extracted_text(
                                page["raw_json"],
                                page["url"],
                                extractor=html_extractor,
                            )

                            cur.execute(
                                """
                                SELECT id, raw_json
                                FROM pages
                                WHERE lecture_id = %s
                                  AND (
                                    page_number = %s
                                    OR title = %s
                                    OR url = %s
                                  )
                                LIMIT 1;
                                """,
                                (
                                    lecture_id,
                                    page["page_number"],
                                    page["title"],
                                    page["url"],
                                ),
                            )
                            existing_page_row = cur.fetchone()
                            if existing_page_row:
                                existing_extracted_text = content_excerpt_from_raw_json(
                                    existing_page_row[1],
                                    HTML_EXTRACTED_TEXT_LIMIT,
                                )
                                if (
                                    existing_extracted_text
                                    and not looks_like_moocs_login_page("", existing_extracted_text)
                                    and isinstance(page_raw_json, dict)
                                    and not page_raw_json.get("extracted_text")
                                ):
                                    page_raw_json["extracted_text"] = existing_extracted_text

                                cur.execute(
                                    """
                                    UPDATE pages
                                    SET
                                        title = COALESCE(%s, title),
                                        url = COALESCE(%s, url),
                                        raw_json = %s::jsonb
                                    WHERE id = %s;
                                    """,
                                    (
                                        page["title"] or None,
                                        page["url"] or None,
                                        json.dumps(page_raw_json, ensure_ascii=False),
                                        existing_page_row[0],
                                    ),
                                )
                                updated += 1
                                continue

                            cur.execute(
                                """
                                INSERT INTO pages (
                                    lecture_id,
                                    page_number,
                                    title,
                                    url,
                                    raw_json
                                )
                                VALUES (%s, %s, %s, %s, %s::jsonb);
                                """,
                                (
                                    lecture_id,
                                    page["page_number"],
                                    page["title"] or None,
                                    page["url"] or None,
                                    json.dumps(page_raw_json, ensure_ascii=False),
                                ),
                            )
                            imported += 1
                if not dry_run:
                    conn.commit()
        finally:
            if html_extractor is not None:
                html_extractor.close()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    if not found_page_metadata:
        return {
            "status": "ok",
            "imported": 0,
            "message": "page metadata not found in moocs_course_details.json",
        }

    return {
        "status": "ok",
        "dry_run": dry_run,
        "course_code": requested_course_code or None,
        "page_limit": page_limit,
        "planned": planned,
        "imported": imported,
        "updated": updated,
        "skipped_missing_lecture": skipped_missing_lecture,
    }


@app.post("/api/import-materials")
def import_materials():
    database_url, error = get_database_url()
    if error:
        return error

    if not COURSE_DETAILS_PATH.exists():
        return {
            "status": "error",
            "detail": "moocs_course_details.json not found",
        }

    try:
        raw_courses = json.loads(COURSE_DETAILS_PATH.read_text(encoding="utf-8"))
        imported = 0
        found_material_metadata = False

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for course in raw_courses:
                    if not isinstance(course, dict):
                        continue

                    course_code = extract_course_code(course)
                    if not course_code:
                        continue

                    material_items = extract_material_items(course)
                    if not material_items:
                        continue

                    found_material_metadata = True

                    cur.execute(
                        "SELECT id FROM courses WHERE course_code = %s;",
                        (course_code,),
                    )
                    course_row = cur.fetchone()
                    if not course_row:
                        continue

                    course_id = course_row[0]

                    for material in material_items:
                        cur.execute(
                            """
                            SELECT id
                            FROM lectures
                            WHERE course_id = %s
                              AND (
                                lecture_number = %s
                                OR title = %s
                              )
                            LIMIT 1;
                            """,
                            (
                                course_id,
                                material["lecture_number"],
                                material["lecture_title"],
                            ),
                        )
                        lecture_row = cur.fetchone()
                        if not lecture_row:
                            continue

                        lecture_id = lecture_row[0]

                        cur.execute(
                            """
                            SELECT id
                            FROM pages
                            WHERE lecture_id = %s
                              AND (
                                page_number = %s
                                OR title = %s
                                OR url = %s
                              )
                            LIMIT 1;
                            """,
                            (
                                lecture_id,
                                material["page_number"],
                                material["page_title"],
                                material["page_url"],
                            ),
                        )
                        page_row = cur.fetchone()
                        if not page_row:
                            continue

                        page_id = page_row[0]

                        cur.execute(
                            """
                            SELECT id
                            FROM materials
                            WHERE page_id = %s
                              AND (
                                material_number = %s
                                OR url = %s
                              )
                            LIMIT 1;
                            """,
                            (
                                page_id,
                                material["material_number"],
                                material["url"],
                            ),
                        )
                        if cur.fetchone():
                            continue

                        cur.execute(
                            """
                            INSERT INTO materials (
                                page_id,
                                material_number,
                                material_type,
                                url,
                                retrieval_method,
                                raw_json
                            )
                            VALUES (%s, %s, %s, %s, %s, %s::jsonb);
                            """,
                            (
                                page_id,
                                material["material_number"],
                                material["material_type"] or None,
                                material["url"] or None,
                                material["retrieval_method"] or None,
                                json.dumps(material["raw_json"], ensure_ascii=False),
                            ),
                        )
                        imported += 1
            conn.commit()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    if not found_material_metadata:
        return {
            "status": "ok",
            "imported": 0,
            "message": "material metadata not found in moocs_course_details.json",
        }

    return {
        "status": "ok",
        "imported": imported,
    }


@app.get("/api/import-tasks")
@app.post("/api/import-tasks")
def import_tasks():
    database_url, error = get_database_url()
    if error:
        return error

    if not COURSE_DETAILS_PATH.exists():
        return {
            "status": "error",
            "detail": "moocs_course_details.json not found",
        }

    try:
        raw_courses = json.loads(COURSE_DETAILS_PATH.read_text(encoding="utf-8"))
        imported = 0
        found_task_metadata = False

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for course in raw_courses:
                    if not isinstance(course, dict):
                        continue

                    course_code = extract_course_code(course)
                    if not course_code:
                        continue

                    task_items = extract_task_items(course)
                    if not task_items:
                        continue

                    found_task_metadata = True

                    cur.execute(
                        "SELECT id FROM courses WHERE course_code = %s;",
                        (course_code,),
                    )
                    course_row = cur.fetchone()
                    if not course_row:
                        continue

                    course_id = course_row[0]

                    for task in task_items:
                        cur.execute(
                            """
                            SELECT id
                            FROM lectures
                            WHERE course_id = %s
                              AND (
                                lecture_number = %s
                                OR title = %s
                              )
                            LIMIT 1;
                            """,
                            (
                                course_id,
                                task["lecture_number"],
                                task["lecture_title"],
                            ),
                        )
                        lecture_row = cur.fetchone()
                        lecture_id = lecture_row[0] if lecture_row else None

                        cur.execute(
                            """
                            SELECT id
                            FROM tasks
                            WHERE course_id = %s
                              AND title = %s
                              AND COALESCE(source_url, '') = COALESCE(%s, '')
                            LIMIT 1;
                            """,
                            (
                                course_id,
                                task["title"],
                                task["source_url"] or None,
                            ),
                        )
                        if cur.fetchone():
                            continue

                        cur.execute(
                            """
                            INSERT INTO tasks (
                                course_id,
                                lecture_id,
                                title,
                                status,
                                due_date,
                                source_type,
                                source_url,
                                raw_json
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb);
                            """,
                            (
                                course_id,
                                lecture_id,
                                task["title"],
                                None,
                                normalize_due_date(task["due_date"]),
                                task["source_type"],
                                task["source_url"] or None,
                                json.dumps(task["raw_json"], ensure_ascii=False),
                            ),
                        )
                        imported += 1
            conn.commit()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    if not found_task_metadata:
        return {
            "status": "ok",
            "imported": 0,
            "message": "task metadata not found in moocs_course_details.json",
        }

    return {
        "status": "ok",
        "imported": imported,
    }


@app.post("/api/import-moocs-details")
def import_moocs_details():
    import_steps = [
        ("courses", import_courses),
        ("lectures", import_lectures),
        ("materials", import_materials),
        ("tasks", import_tasks),
    ]
    results = {}

    for name, import_step in import_steps:
        result = import_step()
        results[name] = result
        if result.get("status") != "ok":
            return {
                "status": "error",
                "failed_step": name,
                "results": results,
            }

    try:
        results["search_index"] = {
            "status": "ok",
            "indexed": reindex_search_documents(),
        }
    except Exception as exc:
        results["search_index"] = {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "results": results,
    }


@app.get("/api/courses")
def list_courses():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, course_code, title "
                    "FROM courses "
                    "ORDER BY id;"
                )
                courses = [
                    {
                        "id": row[0],
                        "course_code": row[1],
                        "title": row[2],
                    }
                    for row in cur.fetchall()
                ]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "courses": courses,
    }


@app.get("/api/lectures")
def list_lectures():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, course_id, lecture_number, title "
                    "FROM lectures "
                    "ORDER BY course_id, lecture_number, id;"
                )
                lectures = [
                    {
                        "id": row[0],
                        "course_id": row[1],
                        "lecture_number": row[2],
                        "title": row[3],
                    }
                    for row in cur.fetchall()
                ]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "lectures": lectures,
    }


@app.get("/api/pages")
def list_pages():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, lecture_id, page_number, title, url "
                    "FROM pages "
                    "ORDER BY lecture_id, page_number, id;"
                )
                pages = [
                    {
                        "id": row[0],
                        "lecture_id": row[1],
                        "page_number": row[2],
                        "title": row[3],
                        "url": row[4],
                    }
                    for row in cur.fetchall()
                ]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "pages": pages,
    }


@app.get("/api/materials")
def list_materials():
    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, page_id, material_number, "
                    "material_type, url, retrieval_method "
                    "FROM materials "
                    "ORDER BY page_id, material_number, id;"
                )
                materials = [
                    {
                        "id": row[0],
                        "page_id": row[1],
                        "material_number": row[2],
                        "material_type": row[3],
                        "url": row[4],
                        "retrieval_method": row[5],
                    }
                    for row in cur.fetchall()
                ]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "materials": materials,
    }


def build_rule_task_list_response(course_codes):
    normalized_course_codes, items, warnings = build_rule_task_items(course_codes)
    response_items = []
    for item in items:
        item_dict = task_list_item_summary(item)
        response_items.append(item_dict)

    return {
        "course_codes": normalized_course_codes,
        "task_count": len(response_items),
        "active_count": sum(1 for item in response_items if item["active"]),
        "warnings": warnings,
        "items": response_items,
    }


def build_rule_task_items(course_codes):
    ensure_user_task_statuses_loaded()
    normalized_course_codes = [normalize_course_code(code) for code in course_codes]
    tasks = []
    warnings = list(USER_TASK_STATUS_WARNINGS)

    for course_code in normalized_course_codes:
        course_tasks = generate_course_rule_tasks(course_code)
        if not course_tasks:
            warnings.append(
                {
                    "course_code": course_code,
                    "message": "No course rule tasks generated.",
                }
            )
        tasks.extend(course_tasks)

    html_evidence, html_warnings = load_html_evidence_by_course(
        normalized_course_codes,
        HTML_EVIDENCE_PATH,
    )
    warnings.extend(html_warnings)
    slides_evidence, slides_warnings = load_slides_evidence_by_course(
        normalized_course_codes,
        HTML_EVIDENCE_PATH,
        moocs_collect_db_path=MOOCS_COLLECT_DB_PATH,
    )
    warnings.extend(slides_warnings)

    items = compose_task_list_items(
        tasks,
        USER_TASK_STATUSES,
        extra_evidence=merge_task_evidence(html_evidence, slides_evidence),
    )
    return normalized_course_codes, items, warnings


def task_list_item_summary(item):
    item_dict = asdict(item)
    item_dict["evidence"] = [
        task_evidence_summary(evidence) for evidence in item.evidence
    ]
    item_dict["evidence_detail_url"] = f"/api/tasks/{item.task_id}/evidence"
    return {"id": item.task_id, **item_dict}


def task_evidence_summary(evidence):
    return {
        "type": evidence.type,
        "label": evidence.label,
        "confidence": evidence.confidence,
    }


def merge_task_evidence(*evidence_maps):
    merged = {}
    for evidence_map in evidence_maps:
        for key, evidence_items in evidence_map.items():
            merged.setdefault(key, []).extend(evidence_items)
    return merged


def ensure_user_task_statuses_loaded():
    global USER_TASK_STATUS_LOADED
    if USER_TASK_STATUS_LOADED:
        return

    statuses, warnings = load_user_task_statuses(USER_TASK_STATUS_PATH)
    USER_TASK_STATUSES.clear()
    USER_TASK_STATUSES.update(statuses)
    USER_TASK_STATUS_WARNINGS.clear()
    USER_TASK_STATUS_WARNINGS.extend(warnings)
    USER_TASK_STATUS_LOADED = True


@app.get("/api/tasks")
def list_tasks(course_code: list[str] | None = Query(default=None)):
    if course_code:
        return build_rule_task_list_response(course_code)

    database_url, error = get_database_url()
    if error:
        return error

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, course_id, lecture_id, title, status, "
                    "due_date, source_type, source_url "
                    "FROM tasks "
                    "ORDER BY course_id, lecture_id, id;"
                )
                tasks = [
                    {
                        "id": row[0],
                        "course_id": row[1],
                        "lecture_id": row[2],
                        "title": row[3],
                        "status": row[4],
                        "due_date": row[5].isoformat() if row[5] else None,
                        "source_type": row[6],
                        "source_url": row[7],
                    }
                    for row in cur.fetchall()
                ]
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "tasks": tasks,
    }


@app.get("/api/tasks/pending")
def list_pending_tasks(course_code: list[str] | None = Query(default=None)):
    course_codes = course_code or ["COT101", "SEM101", "COT105"]
    return build_pending_tasks_payload(build_rule_task_list_response(course_codes))


@app.get("/api/tasks/backlog/summary")
def summarize_task_backlog(course_code: list[str] | None = Query(default=None)):
    course_codes = course_code or ["COT101", "SEM101", "COT105"]
    return summarize_task_backlog_payload(build_rule_task_list_response(course_codes))


@app.get("/api/tasks/{task_id}/evidence")
def get_task_evidence(task_id: str, course_code: list[str] | None = Query(default=None)):
    detail_course_codes = course_code or infer_course_codes_for_task(task_id)
    if not detail_course_codes:
        raise HTTPException(status_code=404, detail="Task evidence not found")

    _, items, warnings = build_rule_task_items(detail_course_codes)
    for item in items:
        if item.task_id != task_id:
            continue
        return {
            "task_id": item.task_id,
            "course_code": item.course_code,
            "evidence": [asdict(evidence) for evidence in item.evidence],
            "evidence_omitted_count": item.evidence_omitted_count,
            "warnings": warnings,
        }

    raise HTTPException(status_code=404, detail="Task evidence not found")


def infer_course_codes_for_task(task_id: str):
    if task_id.startswith("course-rule:"):
        course_code = task_id.split(":", 1)[1].strip()
        if course_code:
            return [course_code]
    return []


@app.patch("/api/tasks/{task_id}/status")
def update_task_status(task_id: str, request: TaskStatusUpdateRequest):
    ensure_user_task_statuses_loaded()
    requested_status = request.status.strip().lower()
    if requested_status not in ALLOWED_USER_TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid task status")

    current_status = USER_TASK_STATUSES.get(task_id) or create_default_status(task_id)
    if requested_status == "todo":
        next_status = mark_todo(current_status)
    elif requested_status == "done":
        next_status = mark_done(current_status)
    else:
        next_status = mark_ignored(current_status)

    USER_TASK_STATUSES[task_id] = next_status
    save_user_task_statuses(USER_TASK_STATUS_PATH, USER_TASK_STATUSES)
    return {
        "task_id": next_status.task_id,
        "status": next_status.status,
        "active": next_status.status == "todo",
        "updated_at": (
            next_status.updated_at.isoformat() if next_status.updated_at else None
        ),
        "checked_at": (
            next_status.checked_at.isoformat() if next_status.checked_at else None
        ),
    }


def load_local_resource_index(index_path: Path | None = None):
    resolved_index_path = Path(index_path or LOCAL_RESOURCE_INDEX_PATH).expanduser()
    if not resolved_index_path.exists():
        return [], [
            {
                "message": (
                    "Local resource index has not been generated yet: "
                    f"{resolved_index_path}"
                ),
            }
        ], resolved_index_path

    try:
        data = json.loads(resolved_index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [
            {
                "message": f"Could not read local resource index: {exc}",
            }
        ], resolved_index_path

    raw_resources = data.get("resources", [])
    warnings = list(data.get("warnings", []))
    if not isinstance(raw_resources, list):
        return [], [
            *warnings,
            {
                "message": "Local resource index resources must be an array.",
            },
        ], resolved_index_path

    resources = [
        resource
        for resource in raw_resources
        if isinstance(resource, dict) and resource.get("resource_type") == "pdf"
    ]
    return resources, warnings, resolved_index_path


def local_resource_summary(resource):
    resource_kind = normalize_resource_kind(
        resource.get("resource_kind"),
        fallback=infer_resource_kind(
            resource.get("title"),
            resource.get("course_title"),
            resource.get("lecture_title"),
        ),
    )
    source_kind = normalize_source_kind(
        resource.get("source_kind") or resource.get("discovered_from")
    )
    summary = {
        "resource_id": resource.get("resource_id"),
        "title": resource.get("title"),
        "course_code": resource.get("course_code"),
        "course_title": resource.get("course_title"),
        "lecture_key": resource.get("lecture_key"),
        "lecture_title": resource.get("lecture_title"),
        "resource_type": resource.get("resource_type"),
        "local_path": resource.get("local_path"),
        "text_available": bool(resource.get("text_available")),
        "text_cache_path": resource.get("text_cache_path"),
        "discovered_from": resource.get("discovered_from"),
        "resource_kind": resource_kind,
        "entity_type": resource.get("entity_type") or ENTITY_TYPE_RESOURCE,
        "source_kind": source_kind,
        "warnings": resource.get("warnings") or [],
    }
    summary["card_text"] = str(
        resource.get("card_text") or build_local_resource_card(summary)
    )
    return summary


def local_resource_open_url(resource):
    resource_id = str(resource.get("resource_id") or "")
    return f"/api/local/resources/{quote(resource_id, safe='')}/file"


def find_local_resource(resource_id: str):
    resources, warnings, index_path = load_local_resource_index()
    for resource in resources:
        if resource.get("resource_id") == resource_id:
            return resource, warnings, index_path
    raise HTTPException(status_code=404, detail="Local resource not found")


def resolve_local_text_cache_path(text_cache_path, index_path: Path) -> Path | None:
    if not text_cache_path:
        return None

    candidate = Path(str(text_cache_path)).expanduser()
    if candidate.is_absolute():
        return candidate

    project_candidate = PROJECT_ROOT / candidate
    if project_candidate.exists():
        return project_candidate

    return index_path.parent / candidate


def load_local_text_cache_pages(resource, index_path: Path):
    cache_path = resolve_local_text_cache_path(
        resource.get("text_cache_path"),
        index_path,
    )
    if cache_path is None or not cache_path.exists():
        return []

    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    pages = cache.get("pages", [])
    if not isinstance(pages, list):
        return []

    normalized_pages = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        text = str(page.get("text") or "")
        if not text.strip():
            continue
        normalized_pages.append(
            {
                "page_number": page.get("page_number"),
                "text": text,
            }
        )
    return normalized_pages


def local_text_cache_summary(resource, index_path: Path):
    pages = load_local_text_cache_pages(resource, index_path)
    if not pages:
        return {
            "available": False,
            "path": resource.get("text_cache_path"),
            "page_count": 0,
            "pages": [],
        }

    return {
        "available": True,
        "path": resource.get("text_cache_path"),
        "page_count": len(pages),
        "pages": [
            {
                "page_number": page.get("page_number"),
                "text_preview": make_local_search_snippet(page.get("text") or "", ""),
            }
            for page in pages[:5]
        ],
    }


def local_search_text(value):
    return str(value or "").casefold()


def make_local_search_snippet(text: str, query: str, radius: int = 70) -> str:
    collapsed = " ".join(str(text or "").split())
    if not collapsed:
        return ""

    normalized_query = local_search_text(query)
    if not normalized_query:
        return collapsed[:180]

    position = local_search_text(collapsed).find(normalized_query)
    if position < 0:
        return collapsed[:180]

    start = max(0, position - radius)
    end = min(len(collapsed), position + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(collapsed) else ""
    return f"{prefix}{collapsed[start:end]}{suffix}"


def match_local_resource_metadata(resource, normalized_query: str) -> str | None:
    summary = local_resource_summary(resource)
    fields = [
        summary.get("title"),
        summary.get("course_code"),
        summary.get("course_title"),
        summary.get("lecture_key"),
        summary.get("lecture_title"),
        summary.get("resource_kind"),
        summary.get("source_kind"),
        summary.get("card_text"),
    ]
    for value in fields:
        text = str(value or "")
        if normalized_query in local_search_text(text):
            return text
    return None


def search_local_resource(resource, query: str, index_path: Path):
    normalized_query = local_search_text(query)
    summary = local_resource_summary(resource)
    text_pages = load_local_text_cache_pages(resource, index_path)
    for page in text_pages:
        text = page.get("text") or ""
        if normalized_query in local_search_text(text):
            return {
                **summary,
                "snippet": make_local_search_snippet(text, query),
                "page_number": page.get("page_number"),
                "open_url": local_resource_open_url(resource),
                "search_mode": "keyword",
            }

    metadata_match = match_local_resource_metadata(resource, normalized_query)
    if metadata_match is None:
        return None

    metadata_text = " / ".join(
        str(value)
        for value in (
            summary.get("course_title"),
            summary.get("lecture_key"),
            summary.get("lecture_title"),
            summary.get("title"),
            summary.get("card_text"),
        )
        if value
    )
    return {
        **summary,
        "snippet": make_local_search_snippet(metadata_text or metadata_match, query),
        "page_number": None,
        "open_url": local_resource_open_url(resource),
        "search_mode": "keyword",
    }


def search_local_resources_keyword(resources, query: str, index_path: Path):
    results = []
    for resource in resources:
        result = search_local_resource(resource, query, index_path)
        if result is not None:
            results.append(result)
    return results


def search_local_resources_semantic(resources, query: str, index_path: Path):
    query_vector = LOCAL_EMBEDDING_PROVIDER.embed(query)
    results = []
    for resource in resources:
        summary = local_resource_summary(resource)
        document_text = local_resource_semantic_document(summary, index_path)
        score = cosine_similarity(
            query_vector,
            LOCAL_EMBEDDING_PROVIDER.embed(document_text),
        )
        if score <= 0:
            continue
        results.append(
            {
                **summary,
                "snippet": make_local_search_snippet(
                    summary.get("card_text") or document_text,
                    query,
                ),
                "page_number": None,
                "open_url": local_resource_open_url(resource),
                "search_mode": "semantic",
                "search_score": round(score, 4),
            }
        )
    results.sort(key=lambda item: item.get("search_score", 0), reverse=True)
    return results


def search_local_resources_hybrid(resources, query: str, index_path: Path):
    merged = {}
    resource_to_key = {}
    for rank, result in enumerate(
        search_local_resources_keyword(resources, query, index_path)
    ):
        key = f"{result.get('resource_id')}:{result.get('page_number')}"
        merged[key] = {
            **result,
            "search_mode": "hybrid",
            "search_score": round(2.0 + max(0.0, 1.0 - (rank * 0.01)), 4),
        }
        resource_to_key.setdefault(result.get("resource_id"), key)

    for result in search_local_resources_semantic(resources, query, index_path):
        resource_id = result.get("resource_id")
        if resource_id in resource_to_key:
            key = resource_to_key[resource_id]
            merged[key]["search_score"] = round(
                merged[key].get("search_score", 0) + result.get("search_score", 0),
                4,
            )
            continue

        key = f"{resource_id}:semantic"
        merged[key] = {
            **result,
            "search_mode": "hybrid",
        }

    results = list(merged.values())
    results.sort(key=lambda item: item.get("search_score", 0), reverse=True)
    return results


def local_resource_semantic_document(summary, index_path: Path):
    return " ".join(
        str(value or "")
        for value in (
            summary.get("card_text"),
            summary.get("title"),
            summary.get("course_code"),
            summary.get("course_title"),
            summary.get("lecture_key"),
            summary.get("lecture_title"),
            summary.get("resource_kind"),
            summary.get("source_kind"),
            summary.get("entity_type"),
        )
    )


def normalize_local_resource_search_mode(mode: str):
    normalized = str(mode or "keyword").strip().casefold()
    return normalized if normalized in LOCAL_RESOURCE_SEARCH_MODES else None


@app.get("/api/local/resources")
def list_local_resources():
    resources, warnings, _ = load_local_resource_index()
    return {
        "status": "ok",
        "resource_count": len(resources),
        "warnings": warnings,
        "resources": [
            {
                **local_resource_summary(resource),
                "open_url": local_resource_open_url(resource),
            }
            for resource in resources
        ],
    }


@app.get("/api/local/resources/search")
def search_local_resources(q: str = "", limit: int = 20, mode: str = "keyword"):
    query = q.strip()
    if not query:
        return {
            "status": "error",
            "detail": "query parameter q is required",
            "query": query,
            "mode": mode,
            "results": [],
        }

    search_mode = normalize_local_resource_search_mode(mode)
    if search_mode is None:
        return {
            "status": "error",
            "detail": "mode must be one of: keyword, semantic, hybrid",
            "query": query,
            "mode": mode,
            "results": [],
        }

    normalized_limit = max(1, min(limit, 50))
    resources, warnings, index_path = load_local_resource_index()
    if search_mode == "semantic":
        results = search_local_resources_semantic(resources, query, index_path)
    elif search_mode == "hybrid":
        results = search_local_resources_hybrid(resources, query, index_path)
    else:
        results = search_local_resources_keyword(resources, query, index_path)

    return {
        "status": "ok",
        "query": query,
        "mode": search_mode,
        "result_count": len(results[:normalized_limit]),
        "warnings": warnings,
        "results": results[:normalized_limit],
    }


@app.get("/api/local/resources/{resource_id}")
def get_local_resource(resource_id: str):
    resource, warnings, index_path = find_local_resource(resource_id)
    return {
        "status": "ok",
        "warnings": warnings,
        "resource": {
            **local_resource_summary(resource),
            "open_url": local_resource_open_url(resource),
            "text_cache": local_text_cache_summary(resource, index_path),
        },
    }


@app.get("/api/local/resources/{resource_id}/file")
def open_local_resource_file(resource_id: str):
    resource, _, _ = find_local_resource(resource_id)
    local_path = resource.get("local_path")
    if not local_path:
        raise HTTPException(status_code=404, detail="Local PDF path is missing")

    pdf_path = Path(str(local_path)).expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.casefold() != ".pdf":
        raise HTTPException(status_code=404, detail="Local PDF file not found")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=resource.get("title") or pdf_path.name,
    )


def load_materials_for_api():
    materials, warnings = load_material_text_index(MATERIAL_TEXT_INDEX_PATH)
    if materials:
        return materials, warnings

    resources, resource_warnings, index_path = load_local_resource_index()
    fallback_materials = material_texts_from_local_resources(
        resources,
        index_path=index_path,
        include_text_cache=True,
        base_url=None,
    )
    return fallback_materials, [
        *warnings,
        *resource_warnings,
        {
            "message": (
                "Material text index was not available; using transient "
                "metadata/PDF text-cache fallback from resource_index.json."
            )
        },
    ]


def load_chunks_for_api():
    chunks, warnings = load_material_chunk_index(MATERIAL_CHUNK_INDEX_PATH)
    if chunks:
        return chunks, warnings

    materials, material_warnings = load_materials_for_api()
    return chunk_material_texts(materials), [
        *warnings,
        *material_warnings,
        {
            "message": (
                "Material chunk index was not available; chunks were built in memory."
            )
        },
    ]


def material_public_summary(material, *, include_full_text=False, max_text_chars=4000):
    data = material.to_dict(include_text=include_full_text)
    if include_full_text:
        text = data.get("text") or ""
        if len(text) > max_text_chars:
            data["text"] = text[:max_text_chars].rstrip()
            data["truncated"] = True
        else:
            data["truncated"] = False
    else:
        data["text_preview"] = make_local_search_snippet(material.text, "")
    return data


def find_material_for_api(material_id: str):
    materials, warnings = load_materials_for_api()
    for material in materials:
        if material.material_id == material_id or material.local_resource_id == material_id:
            return material, warnings
    raise HTTPException(status_code=404, detail="Material not found")


def material_search_filters(
    course_code=None,
    course_title=None,
    lecture_key=None,
    lecture_title=None,
    source_type=None,
    resource_kind=None,
    entity_type=None,
):
    return {
        "course_code": course_code,
        "course_title": course_title,
        "lecture_key": lecture_key,
        "lecture_title": lecture_title,
        "source_type": source_type,
        "resource_kind": resource_kind,
        "entity_type": entity_type,
    }


@app.get("/api/materials")
def list_materials(limit: int = 100):
    materials, warnings = load_materials_for_api()
    normalized_limit = max(1, min(limit, 500))
    return {
        "status": "ok",
        "material_count": len(materials),
        "warnings": warnings,
        "materials": [
            material_public_summary(material, include_full_text=False)
            for material in materials[:normalized_limit]
        ],
        "caution": MATERIAL_SEARCH_CAUTION,
    }


@app.get("/api/materials/search")
def search_materials(
    q: str = "",
    mode: str = "keyword",
    limit: int = 10,
    course_code: str | None = None,
    course_title: str | None = None,
    lecture_key: str | None = None,
    lecture_title: str | None = None,
    source_type: str | None = None,
    resource_kind: str | None = None,
    entity_type: str | None = None,
):
    query = q.strip()
    if not query:
        return {
            "status": "error",
            "detail": "query parameter q is required",
            "query": query,
            "results": [],
            "caution": MATERIAL_SEARCH_CAUTION,
        }
    search_mode = normalize_material_search_mode(mode)
    if search_mode is None:
        return {
            "status": "error",
            "detail": "mode must be one of: keyword, semantic, hybrid",
            "query": query,
            "mode": mode,
            "results": [],
            "caution": MATERIAL_SEARCH_CAUTION,
        }
    chunks, warnings = load_chunks_for_api()
    results = search_material_chunks(
        chunks,
        query=query,
        mode=search_mode,
        limit=limit,
        filters=material_search_filters(
            course_code,
            course_title,
            lecture_key,
            lecture_title,
            source_type,
            resource_kind,
            entity_type,
        ),
    )
    return {
        "status": "ok",
        "query": query,
        "mode": search_mode,
        "result_count": len(results),
        "warnings": warnings,
        "results": results,
        "caution": MATERIAL_SEARCH_CAUTION,
    }


@app.get("/api/context/search")
def search_context(
    q: str = "",
    mode: str = "hybrid",
    limit: int = 10,
    course_code: str | None = None,
    course_title: str | None = None,
    lecture_key: str | None = None,
    lecture_title: str | None = None,
    source_type: str | None = None,
    resource_kind: str | None = None,
    entity_type: str | None = None,
):
    query = q.strip()
    if not query:
        return {
            "status": "error",
            "detail": "query parameter q is required",
            "query": query,
            "items": [],
            "caution": MATERIAL_SEARCH_CAUTION,
        }
    chunks, warnings = load_chunks_for_api()
    try:
        pack = search_context_pack(
            chunks,
            query=query,
            mode=mode,
            limit=limit,
            filters=material_search_filters(
                course_code,
                course_title,
                lecture_key,
                lecture_title,
                source_type,
                resource_kind,
                entity_type,
            ),
        )
    except ValueError as exc:
        return {
            "status": "error",
            "detail": str(exc),
            "query": query,
            "items": [],
            "caution": MATERIAL_SEARCH_CAUTION,
        }
    pack["warnings"] = warnings
    return pack


@app.get("/api/materials/{material_id}/chunks")
def get_material_chunks(material_id: str, limit: int = 20):
    material, warnings = find_material_for_api(material_id)
    chunks, chunk_warnings = load_chunks_for_api()
    material_chunks = [
        chunk.to_dict()
        for chunk in chunks
        if chunk.material_id == material.material_id
        or (
            material.local_resource_id
            and chunk.local_resource_id == material.local_resource_id
        )
    ]
    normalized_limit = max(1, min(limit, 100))
    return {
        "status": "ok",
        "material_id": material.material_id,
        "chunks": material_chunks[:normalized_limit],
        "chunk_count": len(material_chunks),
        "warnings": [*warnings, *chunk_warnings],
        "caution": MATERIAL_SEARCH_CAUTION,
    }


@app.get("/api/materials/{material_id}")
def get_material(
    material_id: str,
    include_full_text: bool = False,
    max_text_chars: int = 4000,
):
    material, warnings = find_material_for_api(material_id)
    chunks, chunk_warnings = load_chunks_for_api()
    related_chunks = [
        chunk.to_dict()
        for chunk in chunks
        if chunk.material_id == material.material_id
        or (
            material.local_resource_id
            and chunk.local_resource_id == material.local_resource_id
        )
    ][:5]
    return {
        "status": "ok",
        "material": material_public_summary(
            material,
            include_full_text=include_full_text,
            max_text_chars=max(500, min(max_text_chars, 20000)),
        ),
        "chunks": related_chunks,
        "warnings": [*warnings, *chunk_warnings],
        "caution": MATERIAL_SEARCH_CAUTION,
    }


def get_meili_client():
    meili_url = os.getenv("MEILI_URL", DEFAULT_MEILI_URL)
    meili_master_key = os.getenv("MEILI_MASTER_KEY", DEFAULT_MEILI_MASTER_KEY)
    return meilisearch.Client(meili_url, meili_master_key)


def get_meili_index(client=None):
    client = client or get_meili_client()
    index_name = os.getenv("MEILI_INDEX", DEFAULT_MEILI_INDEX)
    return client.index(index_name)


def wait_meili_task(client, task):
    task_uid = task.get("taskUid") if isinstance(task, dict) else None
    if task_uid is not None:
        result = client.wait_for_task(task_uid)
        if result.get("status") == "failed":
            error = result.get("error") or {}
            raise RuntimeError(error.get("message", "Meilisearch task failed"))


def configure_meili_index(client=None):
    client = client or get_meili_client()
    index = get_meili_index(client)
    wait_meili_task(client, index.update_searchable_attributes(MEILI_SEARCHABLE_ATTRIBUTES))
    wait_meili_task(client, index.update_filterable_attributes(MEILI_FILTERABLE_ATTRIBUTES))
    wait_meili_task(client, index.update_sortable_attributes(MEILI_SORTABLE_ATTRIBUTES))
    return index


def search_text_for_document(document):
    return " ".join(
        str(document.get(key) or "")
        for key in (
            "course_code",
            "course_title",
            "lecture_title",
            "lecture_number",
            "title",
            "content_excerpt",
            "snippet",
            "source_url",
            "type",
        )
    ).strip()


def make_search_document(
    item_type,
    db_id,
    course_id=None,
    lecture_id=None,
    title=None,
    course_code=None,
    course_title=None,
    lecture_title=None,
    lecture_number=None,
    page_id=None,
    page_number=None,
    source_url=None,
    content_excerpt=None,
):
    snippet = truncate_text(content_excerpt)
    document = {
        "id": f"{item_type}-{db_id}",
        "type": item_type,
        "db_id": db_id,
        "course_id": course_id,
        "lecture_id": lecture_id,
        "title": title,
        "course_code": course_code,
        "course_title": course_title,
        "lecture_title": lecture_title,
        "lecture_number": lecture_number,
        "page_id": page_id,
        "page_number": page_number,
        "source_url": source_url,
        "content_excerpt": snippet,
        "snippet": snippet,
    }
    document["search_text"] = search_text_for_document(document)
    return document


def fetch_search_documents():
    database_url, error = get_database_url()
    if error:
        raise RuntimeError(error.get("detail", "DATABASE_URL is not set"))

    documents = []
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, course_code, title
                FROM courses
                ORDER BY id;
                """
            )
            for row in cur.fetchall():
                documents.append(
                    make_search_document(
                        "course",
                        row[0],
                        course_id=row[0],
                        title=row[2],
                        course_code=row[1],
                        course_title=row[2],
                    )
                )

            cur.execute(
                """
                SELECT
                    lectures.id,
                    lectures.course_id,
                    lectures.lecture_number,
                    lectures.title,
                    courses.course_code,
                    courses.title
                FROM lectures
                LEFT JOIN courses ON courses.id = lectures.course_id
                ORDER BY lectures.course_id, lectures.lecture_number, lectures.id;
                """
            )
            for row in cur.fetchall():
                documents.append(
                    make_search_document(
                        "lecture",
                        row[0],
                        course_id=row[1],
                        lecture_id=row[0],
                        title=row[3],
                        course_code=row[4],
                        course_title=row[5],
                        lecture_title=row[3],
                        lecture_number=row[2],
                    )
                )

            cur.execute(
                """
                SELECT
                    pages.id,
                    lectures.course_id,
                    pages.lecture_id,
                    COALESCE(pages.title, pages.url, '(untitled page)') AS title,
                    courses.course_code,
                    courses.title,
                    lectures.title,
                    lectures.lecture_number,
                    pages.page_number,
                    pages.url,
                    pages.raw_json
                FROM pages
                LEFT JOIN lectures ON lectures.id = pages.lecture_id
                LEFT JOIN courses ON courses.id = lectures.course_id
                ORDER BY lectures.course_id, lectures.lecture_number, pages.page_number, pages.id;
                """
            )
            for row in cur.fetchall():
                documents.append(
                    make_search_document(
                        "page",
                        row[0],
                        course_id=row[1],
                        lecture_id=row[2],
                        title=row[3],
                        course_code=row[4],
                        course_title=row[5],
                        lecture_title=row[6],
                        lecture_number=row[7],
                        page_id=row[0],
                        page_number=row[8],
                        source_url=row[9],
                        content_excerpt=content_excerpt_from_raw_json(row[10]),
                    )
                )

            cur.execute(
                """
                SELECT
                    tasks.id,
                    tasks.course_id,
                    tasks.lecture_id,
                    tasks.title,
                    courses.course_code,
                    courses.title,
                    lectures.title,
                    lectures.lecture_number,
                    tasks.source_url,
                    tasks.raw_json
                FROM tasks
                LEFT JOIN courses ON courses.id = tasks.course_id
                LEFT JOIN lectures ON lectures.id = tasks.lecture_id
                ORDER BY tasks.course_id, lectures.lecture_number, tasks.id;
                """
            )
            for row in cur.fetchall():
                documents.append(
                    make_search_document(
                        "task",
                        row[0],
                        course_id=row[1],
                        lecture_id=row[2],
                        title=row[3],
                        course_code=row[4],
                        course_title=row[5],
                        lecture_title=row[6],
                        lecture_number=row[7],
                        source_url=row[8],
                        content_excerpt=content_excerpt_from_raw_json(row[9]),
                    )
                )

            cur.execute(
                """
                SELECT
                    materials.id,
                    lectures.course_id,
                    pages.lecture_id,
                    COALESCE(
                        materials.raw_json->>'material_title',
                        materials.raw_json->>'title',
                        materials.raw_json->>'name',
                        materials.material_type,
                        materials.url,
                        '(untitled material)'
                    ) AS title,
                    courses.course_code,
                    courses.title,
                    lectures.title,
                    lectures.lecture_number,
                    materials.page_id,
                    pages.page_number,
                    materials.url,
                    materials.raw_json
                FROM materials
                LEFT JOIN pages ON pages.id = materials.page_id
                LEFT JOIN lectures ON lectures.id = pages.lecture_id
                LEFT JOIN courses ON courses.id = lectures.course_id
                ORDER BY lectures.course_id, lectures.lecture_number, pages.page_number, materials.material_number, materials.id;
                """
            )
            for row in cur.fetchall():
                documents.append(
                    make_search_document(
                        "material",
                        row[0],
                        course_id=row[1],
                        lecture_id=row[2],
                        title=row[3],
                        course_code=row[4],
                        course_title=row[5],
                        lecture_title=row[6],
                        lecture_number=row[7],
                        page_id=row[8],
                        page_number=row[9],
                        source_url=row[10],
                        content_excerpt=content_excerpt_from_raw_json(row[11]),
                    )
                )

    return documents


def reindex_search_documents():
    client = get_meili_client()
    index = configure_meili_index(client)
    documents = fetch_search_documents()
    wait_meili_task(client, index.delete_all_documents())
    if documents:
        wait_meili_task(client, index.add_documents(documents, primary_key="id"))
    return len(documents)


def meili_hit_to_search_result(hit):
    return {
        "type": hit.get("type"),
        "id": hit.get("db_id"),
        "course_id": hit.get("course_id"),
        "lecture_id": hit.get("lecture_id"),
        "title": hit.get("title"),
        "course_code": hit.get("course_code"),
        "course_title": hit.get("course_title"),
        "lecture_title": hit.get("lecture_title"),
        "lecture_number": hit.get("lecture_number"),
        "page_id": hit.get("page_id"),
        "page_number": hit.get("page_number"),
        "source_url": hit.get("source_url"),
        "snippet": hit.get("snippet") or hit.get("content_excerpt"),
        "content_excerpt": hit.get("content_excerpt") or hit.get("snippet"),
    }


def enrich_results_with_content(results):
    if not results:
        return results

    database_url, error = get_database_url()
    if error:
        return results

    ids_by_type = {}
    for result in results:
        result_type = result.get("type")
        result_id = result.get("id")
        if result_type in {"page", "material", "task"} and result_id is not None:
            ids_by_type.setdefault(result_type, set()).add(result_id)

    if not ids_by_type:
        return results

    table_by_type = {
        "page": "pages",
        "material": "materials",
        "task": "tasks",
    }
    excerpts = {}

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for result_type, result_ids in ids_by_type.items():
                    table = table_by_type[result_type]
                    cur.execute(
                        f"SELECT id, raw_json FROM {table} WHERE id = ANY(%s);",
                        (list(result_ids),),
                    )
                    for row in cur.fetchall():
                        excerpt = content_excerpt_from_raw_json(row[1])
                        if excerpt:
                            excerpts[(result_type, row[0])] = excerpt
    except Exception:
        return results

    for result in results:
        excerpt = excerpts.get((result.get("type"), result.get("id")))
        if excerpt:
            result["snippet"] = excerpt
            result["content_excerpt"] = excerpt

    return results


def search_meili_data(query, limit):
    index = get_meili_index()
    candidate_limit = max(limit, min(limit * 12, 120))
    meili_query = meili_query_text(query)
    query_intent = search_query_intent(query)
    task_query = query_intent == "task"
    recent_query = looks_like_recent_task_query(query)
    specific_text = specific_query_text(query) if task_query else ""
    response = index.search(meili_query, {"limit": candidate_limit})
    hits = response.get("hits", [])
    if task_query:
        task_response = index.search(
            meili_query,
            {
                "limit": candidate_limit,
                "filter": meili_task_filter(query),
            },
        )
        seen = {hit.get("id") for hit in hits}
        hits.extend(
            hit
            for hit in task_response.get("hits", [])
            if hit.get("id") not in seen
        )
        if recent_query or not specific_text:
            broad_task_response = index.search(
                "",
                {
                    "limit": candidate_limit,
                    "filter": meili_task_filter(query),
                    "sort": ["lecture_number:desc", "db_id:asc"],
                },
            )
            seen = {hit.get("id") for hit in hits}
            hits.extend(
                hit
                for hit in broad_task_response.get("hits", [])
                if hit.get("id") not in seen
            )

    if query_intent == "course_overview":
        overview_filter = meili_course_filter(query)
        overview_filters = []
        if overview_filter:
            overview_filters = [
                f"type = course AND {overview_filter}",
                f"type = lecture AND {overview_filter}",
            ]
        else:
            overview_filters = ["type = course", "type = lecture"]

        seen = {hit.get("id") for hit in hits}
        for filter_expression in overview_filters:
            overview_response = index.search(
                meili_query,
                {
                    "limit": candidate_limit,
                    "filter": filter_expression,
                },
            )
            hits.extend(
                hit
                for hit in overview_response.get("hits", [])
                if hit.get("id") not in seen
            )
            seen = {hit.get("id") for hit in hits}

    results = [meili_hit_to_search_result(hit) for hit in hits]
    type_orders = {
        "task": {
            "task": 0,
            "page": 1,
            "lecture": 2,
            "course": 3,
        },
        "content": {
            "lecture": 0,
            "page": 1,
            "course": 2,
            "material": 3,
            "task": 8,
        },
        "course_overview": {
            "course": 0,
            "lecture": 1,
            "page": 2,
            "material": 3,
            "task": 8,
        },
    }
    type_order = type_orders.get(query_intent)
    if type_order:

        def rank_key(indexed_item):
            original_rank, item = indexed_item
            lecture_number = item.get("lecture_number") or -1
            type_penalty = type_order.get(item.get("type"), 9)
            course_penalty = course_code_penalty(item, query)

            if query_intent == "task":
                related_penalty = 0 if item_matches_specific_query(item, specific_text) else 1
                if recent_query:
                    return (
                        course_penalty,
                        related_penalty,
                        type_penalty,
                        -lecture_number,
                        original_rank,
                    )
                if specific_text:
                    return (
                        course_penalty,
                        related_penalty,
                        type_penalty,
                        original_rank,
                        -lecture_number,
                    )
                return (
                    course_penalty,
                    type_penalty,
                    -lecture_number,
                    original_rank,
                )

            return (
                course_penalty,
                type_penalty,
                original_rank,
                lecture_number if query_intent == "course_overview" else 0,
            )

        results = [
            item
            for _, item in sorted(
                enumerate(results),
                key=rank_key,
            )
        ]
    return enrich_results_with_content(results[:limit])


@app.post("/api/reindex-search")
def reindex_search():
    try:
        indexed = reindex_search_documents()
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "indexed": indexed,
    }


def search_postgresql_data(q: str = "", limit: int = 50):
    query = q.strip()
    if not query:
        return {
            "status": "error",
            "detail": "query parameter q is required",
        }

    database_url, error = get_database_url()
    if error:
        return error

    normalized_limit = max(1, min(limit, 100))
    task_query = looks_like_task_query(query)

    search_keyword = query
    normalized_query = (
        query.lower()
        .replace("１", "1")
        .replace("Ⅰ", "i")
        .replace("ⅰ", "i")
    )
    if any(
        alias in normalized_query
        for alias in (
            "cs概論",
            "cs演習",
            "cot101",
            "コンピュータ・サイエンス",
        )
    ):
        search_keyword = "COT101"
    elif "システムガイダンス" in query:
        search_keyword = "システムガイダンス"
    elif "システム" in query:
        search_keyword = "システム"
    elif "ガイダンス" in query:
        search_keyword = "ガイダンス"
    elif "受講方法" in query:
        search_keyword = "受講方法"
    elif task_query:
        search_keyword = "課題"

    pattern = f"%{search_keyword}%"

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH search_results AS (
                        SELECT
                            'course' AS type,
                            courses.id,
                            courses.id AS course_id,
                            NULL::integer AS lecture_id,
                            courses.title,
                            courses.course_code,
                            NULL::text AS course_title,
                            NULL::text AS lecture_title,
                            NULL::integer AS lecture_number,
                            NULL::integer AS page_id,
                            NULL::integer AS page_number,
                            NULL::text AS source_url,
                            CASE
                                WHEN courses.course_code ILIKE %s THEN 0
                                WHEN courses.title ILIKE %s THEN 1
                                ELSE 5
                            END AS rank,
                            1 AS type_order
                        FROM courses
                        WHERE courses.course_code ILIKE %s
                           OR courses.title ILIKE %s

                        UNION ALL

                        SELECT
                            'lecture' AS type,
                            lectures.id,
                            lectures.course_id,
                            lectures.id AS lecture_id,
                            lectures.title,
                            courses.course_code,
                            courses.title AS course_title,
                            lectures.title AS lecture_title,
                            lectures.lecture_number,
                            NULL::integer AS page_id,
                            NULL::integer AS page_number,
                            NULL::text AS source_url,
                            CASE
                                WHEN lectures.title ILIKE %s THEN 0
                                WHEN courses.course_code ILIKE %s THEN 1
                                WHEN courses.title ILIKE %s THEN 2
                                ELSE 5
                            END AS rank,
                            2 AS type_order
                        FROM lectures
                        LEFT JOIN courses ON courses.id = lectures.course_id
                        WHERE lectures.title ILIKE %s
                           OR CAST(lectures.lecture_number AS text) ILIKE %s
                           OR courses.course_code ILIKE %s
                           OR courses.title ILIKE %s

                        UNION ALL

                        SELECT
                            'task' AS type,
                            tasks.id,
                            tasks.course_id,
                            tasks.lecture_id,
                            tasks.title,
                            courses.course_code,
                            courses.title AS course_title,
                            lectures.title AS lecture_title,
                            lectures.lecture_number,
                            NULL::integer AS page_id,
                            NULL::integer AS page_number,
                            tasks.source_url,
                            CASE
                                WHEN tasks.title ILIKE %s THEN 0
                                WHEN tasks.source_url ILIKE %s THEN 1
                                WHEN courses.course_code ILIKE %s THEN 2
                                WHEN courses.title ILIKE %s THEN 3
                                WHEN lectures.title ILIKE %s THEN 4
                                ELSE 8
                            END AS rank,
                            3 AS type_order
                        FROM tasks
                        LEFT JOIN courses ON courses.id = tasks.course_id
                        LEFT JOIN lectures ON lectures.id = tasks.lecture_id
                        WHERE tasks.title ILIKE %s
                           OR COALESCE(tasks.source_type, '') ILIKE %s
                           OR COALESCE(tasks.source_url, '') ILIKE %s
                           OR COALESCE(tasks.raw_json::text, '') ILIKE %s
                           OR courses.course_code ILIKE %s
                           OR courses.title ILIKE %s
                           OR lectures.title ILIKE %s
                           OR %s

                        UNION ALL

                        SELECT
                            'page' AS type,
                            pages.id,
                            lectures.course_id,
                            pages.lecture_id,
                            COALESCE(pages.title, pages.url, '(untitled page)') AS title,
                            courses.course_code,
                            courses.title AS course_title,
                            lectures.title AS lecture_title,
                            lectures.lecture_number,
                            pages.id AS page_id,
                            pages.page_number,
                            pages.url AS source_url,
                            CASE
                                WHEN pages.title ILIKE %s THEN 0
                                WHEN pages.url ILIKE %s THEN 1
                                WHEN lectures.title ILIKE %s THEN 2
                                WHEN courses.course_code ILIKE %s THEN 3
                                WHEN courses.title ILIKE %s THEN 4
                                ELSE 8
                            END AS rank,
                            4 AS type_order
                        FROM pages
                        LEFT JOIN lectures ON lectures.id = pages.lecture_id
                        LEFT JOIN courses ON courses.id = lectures.course_id
                        WHERE COALESCE(pages.title, '') ILIKE %s
                           OR COALESCE(pages.url, '') ILIKE %s
                           OR COALESCE(pages.raw_json::text, '') ILIKE %s
                           OR lectures.title ILIKE %s
                           OR courses.course_code ILIKE %s
                           OR courses.title ILIKE %s

                        UNION ALL

                        SELECT
                            'material' AS type,
                            materials.id,
                            lectures.course_id,
                            pages.lecture_id,
                            COALESCE(
                                materials.raw_json->>'material_title',
                                materials.raw_json->>'title',
                                materials.raw_json->>'name',
                                materials.material_type,
                                materials.url,
                                '(untitled material)'
                            ) AS title,
                            courses.course_code,
                            courses.title AS course_title,
                            lectures.title AS lecture_title,
                            lectures.lecture_number,
                            materials.page_id,
                            pages.page_number,
                            materials.url AS source_url,
                            CASE
                                WHEN COALESCE(
                                    materials.raw_json->>'material_title',
                                    materials.raw_json->>'title',
                                    materials.raw_json->>'name',
                                    materials.material_type,
                                    materials.url,
                                    ''
                                ) ILIKE %s THEN 0
                                WHEN pages.title ILIKE %s THEN 1
                                WHEN lectures.title ILIKE %s THEN 2
                                WHEN courses.course_code ILIKE %s THEN 3
                                WHEN courses.title ILIKE %s THEN 4
                                ELSE 8
                            END AS rank,
                            5 AS type_order
                        FROM materials
                        LEFT JOIN pages ON pages.id = materials.page_id
                        LEFT JOIN lectures ON lectures.id = pages.lecture_id
                        LEFT JOIN courses ON courses.id = lectures.course_id
                        WHERE COALESCE(
                                  materials.raw_json->>'material_title',
                                  materials.raw_json->>'title',
                                  materials.raw_json->>'name',
                                  materials.material_type,
                                  materials.url,
                                  ''
                              ) ILIKE %s
                           OR COALESCE(materials.retrieval_method, '') ILIKE %s
                           OR COALESCE(materials.raw_json::text, '') ILIKE %s
                           OR COALESCE(pages.title, '') ILIKE %s
                           OR COALESCE(pages.url, '') ILIKE %s
                           OR lectures.title ILIKE %s
                           OR courses.course_code ILIKE %s
                           OR courses.title ILIKE %s
                    )
                    SELECT
                        type,
                        id,
                        course_id,
                        lecture_id,
                        title,
                        course_code,
                        course_title,
                        lecture_title,
                        lecture_number,
                        page_id,
                        page_number,
                        source_url
                    FROM search_results
                    ORDER BY rank, type_order, course_id NULLS LAST,
                             lecture_number NULLS LAST, id
                    LIMIT %s;
                    """,
                    tuple(
                        [pattern] * 23
                        + [task_query]
                        + [pattern] * 24
                        + [normalized_limit]
                    ),
                )
                results = [
                    {
                        "type": row[0],
                        "id": row[1],
                        "course_id": row[2],
                        "lecture_id": row[3],
                        "title": row[4],
                        "course_code": row[5],
                        "course_title": row[6],
                        "lecture_title": row[7],
                        "lecture_number": row[8],
                        "page_id": row[9],
                        "page_number": row[10],
                        "source_url": row[11],
                    }
                    for row in cur.fetchall()
                ]
                results = enrich_results_with_content(results)
    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }

    return {
        "status": "ok",
        "query": query,
        "results": results,
    }


def search_database_data(q: str = "", limit: int = 50):
    query = q.strip()
    if not query:
        return {
            "status": "error",
            "detail": "query parameter q is required",
        }

    normalized_limit = max(1, min(limit, 100))
    try:
        results = search_meili_data(query, normalized_limit)
        return {
            "status": "ok",
            "query": query,
            "results": results,
        }
    except Exception:
        return search_postgresql_data(query, normalized_limit)


@app.get("/api/search")
def search_database(q: str = "", limit: int = 50):
    return utf8_json(search_database_data(q, limit))


FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "frontend"
)

app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend"
)
