import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).with_name(".env"))


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in backend/.env")

    return genai.Client(api_key=api_key)


def _display(value):
    return "" if value is None else value


def _excerpt(value, limit=1000):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def build_context(sources):
    context_lines = []

    for index, source in enumerate(sources, start=1):
        excerpt = source.get("content_excerpt") or source.get("snippet") or ""
        context_lines.append(
            "\n".join(
                [
                    f"source_index: {index}",
                    f"type: {_display(source.get('type', ''))}",
                    f"id: {_display(source.get('id', ''))}",
                    f"course_code: {_display(source.get('course_code', ''))}",
                    f"course_title: {_display(source.get('course_title', ''))}",
                    f"course_id: {_display(source.get('course_id', ''))}",
                    f"lecture_title: {_display(source.get('lecture_title', ''))}",
                    f"lecture_id: {_display(source.get('lecture_id', ''))}",
                    f"lecture_number: {_display(source.get('lecture_number', ''))}",
                    f"title: {_display(source.get('title', ''))}",
                    f"source_url: {_display(source.get('source_url', ''))}",
                    f"content_excerpt: {_excerpt(excerpt)}",
                ]
            )
        )

    if not context_lines:
        return "PostgreSQL検索で該当するMOOCs情報は見つかりませんでした。"

    return "\n\n---\n\n".join(context_lines)


def build_prompt(question, sources):
    context = build_context(sources)

    return f"""
あなたはINIAD-AIOのデモ用アシスタントです。
以下のPostgreSQL検索結果だけを根拠に、質問へ日本語で簡潔に回答してください。

制約:
- 検索結果にない情報は推測しないでください。
- 分からない場合は「検索結果からは分かりません」と明記してください。
- 回答には可能な範囲で course_code, lecture_title, type, title, source_url を含めてください。
- source_url がある場合は、ユーザーが確認できるリンクとして示してください。

質問:
{question}

検索結果:
{context}
"""


def _parts_text(parts):
    texts = []
    for part in parts or []:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "".join(texts)


def extract_response_text(response):
    text = getattr(response, "text", None)
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    extracted = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        extracted.append(_parts_text(getattr(content, "parts", None)))

    return "".join(extracted)


def generate_answer(question, sources):
    prompt = build_prompt(question, sources)

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
    )

    return extract_response_text(response)
