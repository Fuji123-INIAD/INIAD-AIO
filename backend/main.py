from pathlib import Path
from datetime import datetime
import json
import os
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import psycopg
from pydantic import BaseModel

from ai_module import generate_answer
from database import init_db
from search_backend import search

app = FastAPI()
init_db()

SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")
COURSE_DETAILS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "probe" / "moocs_course_details.json"
)


class AskRequest(BaseModel):
    question: str


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
    "小テスト",
    "確認テスト",
    "提出",
    "quiz",
    "assignment",
    "exercise",
    "task",
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


@app.post("/api/ask")
def ask(request: AskRequest):
    question = request.question.strip()

    if not question:
        return {
            "answer": "",
            "sources": [],
            "error": "質問を入力してください。",
        }

    sources = []

    try:
        sources = search(question)
        answer = generate_answer(question, sources)
    except Exception as exc:
        return {
            "answer": "",
            "sources": sources,
            "error": str(exc),
        }

    return {
        "answer": answer,
        "sources": sources,
        "error": None,
    }


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
def import_pages():
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
        found_page_metadata = False

        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                for course in raw_courses:
                    if not isinstance(course, dict):
                        continue

                    course_code = extract_course_code(course)
                    if not course_code:
                        continue

                    page_items = extract_page_items(course)
                    if not page_items:
                        continue

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
                                page["page_number"],
                                page["title"],
                                page["url"],
                            ),
                        )
                        if cur.fetchone():
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
                                json.dumps(page["raw_json"], ensure_ascii=False),
                            ),
                        )
                        imported += 1
            conn.commit()
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
        "imported": imported,
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


@app.get("/api/tasks")
def list_tasks():
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

FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "frontend"
)

app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend"
)
