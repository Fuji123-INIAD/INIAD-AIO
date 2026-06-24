"""Normalize v0.2 MOOCs detail JSON into v0.3 database records."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit


TASK_KEYWORDS = (
    "課題",
    "提出",
    "レポート",
    "小テスト",
    "テスト",
    "演習",
    "宿題",
    "assignment",
    "report",
    "homework",
    "quiz",
    "exercise",
    "task",
    "submit",
)
DEADLINE_KEYS = (
    "deadline_at",
    "deadline",
    "due_at",
    "due_date",
    "due",
)
DESCRIPTION_KEYS = ("description", "body", "content", "text")


def load_course_details_json(path: str | Path) -> Any:
    """Load a MOOCs detail JSON file, rejecting invalid top-level values."""
    source_path = Path(path)
    with source_path.open("r", encoding="utf-8") as source:
        data = json.load(source)
    _course_items(data)
    return data


def normalize_source_key(value: Any) -> str:
    """Return a stable, whitespace-trimmed source key.

    HTTP URLs additionally have normalized scheme/host casing, fragments removed,
    and non-root trailing slashes removed.
    """
    normalized = " ".join(str(value or "").split())
    if not normalized:
        return ""

    parts = urlsplit(normalized)
    if parts.scheme.lower() in {"http", "https"} and parts.netloc:
        path = parts.path
        if path != "/":
            path = path.rstrip("/")
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
        )
    return normalized


def stable_id(kind: str, source_key: str) -> str:
    """Build ``{kind}:{sha1(source_key)}`` for a non-empty source key."""
    normalized_kind = str(kind).strip().lower()
    normalized_key = normalize_source_key(source_key)
    if not normalized_kind or not normalized_key:
        raise ValueError("kind and source_key are required for a stable ID")
    digest = hashlib.sha1(normalized_key.encode("utf-8")).hexdigest()
    return f"{normalized_kind}:{digest}"


def normalize_course_details(
    data: Any,
    now: str | datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Normalize one course or a course list into v0.3 table records."""
    timestamp = _normalize_timestamp(now)
    courses_input = _course_items(data)
    if not courses_input:
        raise ValueError("course details must contain at least one course")

    records: dict[str, list[dict[str, Any]]] = {
        "courses": [],
        "lectures": [],
        "pages": [],
        "materials": [],
        "tasks": [],
    }

    for course_index, raw_course in enumerate(courses_input, start=1):
        course = _as_mapping(raw_course, f"course {course_index}")
        course_title = _first_text(course, "course_title", "title", "name")
        if not course_title:
            raise ValueError(f"course {course_index} has no title")
        course_url = _first_text(course, "course_url", "moocs_url", "url")
        normalized_course_url = normalize_source_key(course_url)
        course_source_key = normalized_course_url or _fallback_key(
            "course", course_title, course_index
        )
        course_id = stable_id("course", course_source_key)
        course_code, year = _course_code_and_year(normalized_course_url)
        records["courses"].append(
            {
                "id": course_id,
                "course_code": course_code,
                "title": course_title,
                "year": year,
                "moocs_url": normalized_course_url or None,
                "source": "moocs",
                "source_key": course_source_key,
                "raw_json": dict(course),
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )

        lessons = _child_list(course, "lessons", "lectures")
        for lecture_index, raw_lesson in enumerate(lessons, start=1):
            lesson = _as_mapping(
                raw_lesson, f"course {course_index} lecture {lecture_index}"
            )
            lecture_title = _first_text(
                lesson, "lesson_title", "lecture_title", "title", "name"
            ) or f"Lecture {lecture_index}"
            lecture_url = _first_text(
                lesson, "lesson_url", "lecture_url", "moocs_url", "url"
            )
            normalized_lecture_url = normalize_source_key(lecture_url)
            lecture_source_key = normalized_lecture_url or _fallback_key(
                course_source_key, "lecture", lecture_title, lecture_index
            )
            lecture_id = stable_id("lecture", lecture_source_key)
            records["lectures"].append(
                {
                    "id": lecture_id,
                    "course_id": course_id,
                    "lecture_number": lecture_index,
                    "title": lecture_title,
                    "moocs_url": normalized_lecture_url or None,
                    "source_key": lecture_source_key,
                    "raw_json": dict(lesson),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )

            pages = _child_list(lesson, "pages")
            for page_index, raw_page in enumerate(pages, start=1):
                page = _as_mapping(
                    raw_page,
                    f"course {course_index} lecture {lecture_index} page {page_index}",
                )
                page_title = _first_text(page, "page_title", "title", "name")
                page_url = _first_text(page, "page_url", "moocs_url", "url")
                normalized_page_url = normalize_source_key(page_url)
                page_source_key = normalized_page_url or _fallback_key(
                    lecture_source_key,
                    "page",
                    page_title or "untitled",
                    page_index,
                )
                page_id = stable_id("page", page_source_key)
                records["pages"].append(
                    {
                        "id": page_id,
                        "lecture_id": lecture_id,
                        "page_number": page_index,
                        "title": page_title or None,
                        "moocs_url": normalized_page_url or None,
                        "source_key": page_source_key,
                        "raw_json": dict(page),
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                )

                material_records: list[dict[str, Any]] = []
                materials = _child_list(page, "materials")
                for material_index, raw_material in enumerate(materials, start=1):
                    material = _as_mapping(
                        raw_material,
                        (
                            f"course {course_index} lecture {lecture_index} "
                            f"page {page_index} material {material_index}"
                        ),
                    )
                    material_title = _first_text(
                        material, "material_title", "title", "name"
                    )
                    material_type = _first_text(
                        material, "material_type", "type", "kind"
                    )
                    material_url = _first_text(
                        material, "material_url", "moocs_url", "url", "href"
                    )
                    normalized_material_url = normalize_source_key(material_url)
                    if normalized_material_url:
                        material_source_key = normalize_source_key(
                            f"{page_source_key}|{normalized_material_url}|{material_index}"
                        )
                    else:
                        material_source_key = _fallback_key(
                            page_source_key,
                            "material",
                            material_title or material_type or "untitled",
                            material_index,
                        )
                    material_id = stable_id("material", material_source_key)
                    material_record = {
                        "id": material_id,
                        "course_id": course_id,
                        "lecture_id": lecture_id,
                        "page_id": page_id,
                        "title": material_title or None,
                        "material_type": material_type or None,
                        "moocs_url": normalized_material_url or None,
                        "local_path": None,
                        "source_key": material_source_key,
                        "raw_json": dict(material),
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                    material_records.append(material_record)
                    records["materials"].append(material_record)

                records["tasks"].extend(
                    extract_task_candidates(
                        page=page,
                        page_record=records["pages"][-1],
                        material_records=material_records,
                        course_id=course_id,
                        lecture_id=lecture_id,
                        now=timestamp,
                    )
                )

    return records


def extract_task_candidates(
    page: Mapping[str, Any],
    page_record: Mapping[str, Any],
    material_records: Iterable[Mapping[str, Any]],
    course_id: str,
    lecture_id: str,
    now: str | datetime | None = None,
) -> list[dict[str, Any]]:
    """Infer simple task records from a page and its normalized materials."""
    timestamp = _normalize_timestamp(now)
    candidates: list[dict[str, Any]] = []
    page_title = _first_text(page, "page_title", "title", "name")
    page_url = normalize_source_key(
        _first_text(page, "page_url", "moocs_url", "url")
    )
    page_type = _first_text(page, "page_type", "type", "kind")

    if _looks_like_task(page_title, page_url, page_type):
        candidates.append(
            _task_record(
                source_key=str(page_record["source_key"]),
                title=page_title or page_url or "Task",
                raw=page,
                course_id=course_id,
                lecture_id=lecture_id,
                page_id=str(page_record["id"]),
                moocs_url=page_url or None,
                timestamp=timestamp,
            )
        )

    for material_record in material_records:
        raw_material = material_record.get("raw_json")
        if not isinstance(raw_material, Mapping):
            raw_material = {}
        title = str(material_record.get("title") or "").strip()
        material_url = str(material_record.get("moocs_url") or "").strip()
        material_type = str(material_record.get("material_type") or "").strip()
        if not _looks_like_task(title, material_url, material_type):
            continue
        candidates.append(
            _task_record(
                source_key=str(material_record["source_key"]),
                title=title or page_title or material_url or "Task",
                raw=raw_material,
                course_id=course_id,
                lecture_id=lecture_id,
                page_id=str(page_record["id"]),
                moocs_url=material_url or page_url or None,
                timestamp=timestamp,
            )
        )

    return candidates


def _task_record(
    *,
    source_key: str,
    title: str,
    raw: Mapping[str, Any],
    course_id: str,
    lecture_id: str,
    page_id: str,
    moocs_url: str | None,
    timestamp: str,
) -> dict[str, Any]:
    normalized_title = _normalized_title(title)
    task_source_key = normalize_source_key(f"{source_key}|{normalized_title}")
    return {
        "id": stable_id("task", task_source_key),
        "course_id": course_id,
        "lecture_id": lecture_id,
        "page_id": page_id,
        "title": title.strip(),
        "description": _first_text(raw, *DESCRIPTION_KEYS) or None,
        "deadline_at": _extract_deadline(raw),
        "moocs_url": moocs_url,
        "source_key": task_source_key,
        "raw_json": dict(raw),
        "first_seen_at": timestamp,
        "last_seen_at": timestamp,
        "updated_at": timestamp,
    }


def _course_items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        if "courses" in data:
            courses = data["courses"]
            if not isinstance(courses, list):
                raise ValueError("courses must be a list")
            return courses
        return [data]
    raise ValueError("course details JSON must be a course object or a list")


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _first_text(value: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, (str, int, float)):
            text = " ".join(str(item).split())
            if text:
                return text
    return ""


def _child_list(value: Mapping[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        if key not in value or value[key] is None:
            continue
        child = value[key]
        if not isinstance(child, list):
            raise ValueError(f"{key} must be a list")
        return child
    return []


def _fallback_key(*parts: Any) -> str:
    values = [normalize_source_key(part) for part in parts]
    return "fallback:" + "|".join(value for value in values if value)


def _course_code_and_year(course_url: str) -> tuple[str | None, int | None]:
    segments = [segment for segment in urlsplit(course_url).path.split("/") if segment]
    if "courses" not in segments:
        return None, None
    index = segments.index("courses")
    year = None
    course_code = None
    if len(segments) > index + 1 and re.fullmatch(r"\d{4}", segments[index + 1]):
        year = int(segments[index + 1])
        if len(segments) > index + 2:
            course_code = segments[index + 2]
    elif len(segments) > index + 1:
        course_code = segments[index + 1]
    return course_code or None, year


def _normalized_title(value: str) -> str:
    return " ".join(value.lower().split())


def _looks_like_task(*values: Any) -> bool:
    haystack = " ".join(str(value or "") for value in values).lower()
    return any(keyword in haystack for keyword in TASK_KEYWORDS)


def _find_value_by_keys(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            if value.get(key) not in (None, ""):
                return value[key]
        for item in value.values():
            found = _find_value_by_keys(item, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_value_by_keys(item, keys)
            if found not in (None, ""):
                return found
    return None


def _extract_deadline(raw: Mapping[str, Any]) -> str | None:
    value = _find_value_by_keys(raw, DEADLINE_KEYS)
    if isinstance(value, datetime):
        return _normalize_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso_candidate):
            return date.fromisoformat(iso_candidate).isoformat()
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _normalize_timestamp(value: str | datetime | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("now must not be empty")
        return value.strip()
    if not isinstance(value, datetime):
        raise TypeError("now must be an ISO string, datetime, or None")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
