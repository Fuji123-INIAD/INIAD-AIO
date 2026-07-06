"""Template-generated context cards for AI handoff."""

from __future__ import annotations

from typing import Any, Mapping


RESOURCE_KIND_LABELS = {
    "material": "資料",
    "assignment": "課題",
    "report": "レポート",
    "guide": "ガイド",
    "unknown": "ローカル資料",
}

SOURCE_KIND_LABELS = {
    "filesystem": "ローカルファイルシステム",
    "moocs_collect": "MOOCs-Collect",
    "course_rule": "授業ルール",
    "html": "MOOCs HTML",
    "slides": "MOOCsスライド",
}


def build_local_resource_card(resource: Mapping[str, Any]) -> str:
    """Build a short human-readable card from local resource metadata."""
    course = _first_text(
        resource.get("course_title"),
        resource.get("course_code"),
        fallback="コース未設定",
    )
    lecture = _lecture_phrase(resource)
    kind = RESOURCE_KIND_LABELS.get(
        _text(resource.get("resource_kind")),
        RESOURCE_KIND_LABELS["unknown"],
    )
    title = _first_text(resource.get("title"), fallback="タイトル未設定")
    source_kind = _first_text(
        resource.get("source_kind"),
        resource.get("discovered_from"),
        fallback="filesystem",
    )
    source_label = SOURCE_KIND_LABELS.get(source_kind, source_kind)
    text_note = "本文テキストは抽出済み" if resource.get("text_available") else "本文テキストは未抽出"

    return (
        f"{course}{lecture}の{kind}。"
        f"PDFタイトルは {title}。"
        f"{source_label}からローカル保存された資料で、{text_note}。"
    )


def build_task_context_card(task: Mapping[str, Any]) -> str:
    """Build a short card for a task list item."""
    course = _first_text(
        task.get("course_title"),
        task.get("display_course_name"),
        task.get("course_code"),
        fallback="コース未設定",
    )
    title = _first_text(task.get("title"), fallback="課題名未設定")
    description = _first_text(task.get("description"), fallback="作業内容未設定")
    deadline = _first_text(
        task.get("deadline_note"),
        task.get("deadline_rule"),
        fallback="締切ルール未設定",
    )
    submission = _first_text(
        task.get("submission_note"),
        task.get("submission_channel"),
        fallback="提出先未設定",
    )
    status = _first_text(task.get("status"), fallback="todo")
    source_kind = _first_text(task.get("source_kind"), task.get("source"), fallback="course_rule")
    source_label = SOURCE_KIND_LABELS.get(source_kind, source_kind)

    return (
        f"{course}の課題。"
        f"タイトルは {title}。"
        f"やることは {description}。"
        f"締切メモは {deadline}。"
        f"提出メモは {submission}。"
        f"状態は {status}。根拠は{source_label}。"
    )


def _lecture_phrase(resource: Mapping[str, Any]) -> str:
    key = _text(resource.get("lecture_key"))
    title = _text(resource.get("lecture_title"))
    if key and title:
        return f" 第{key}回 {title}"
    if key:
        return f" 第{key}回"
    if title:
        return f" {title}"
    return ""


def _first_text(*values: object, fallback: str) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return fallback


def _text(value: object) -> str:
    return str(value or "").strip()
