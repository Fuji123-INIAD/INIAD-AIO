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


def generate_answer(question, sources):
    context_lines = []

    for index, source in enumerate(sources, start=1):
        context_lines.append(
            "\n".join(
                [
                    f"source_index: {index}",
                    f"type: {source.get('type', '')}",
                    f"id: {source.get('id', '')}",
                    f"course_code: {source.get('course_code', '')}",
                    f"course_title: {source.get('course_title', '')}",
                    f"course_id: {source.get('course_id', '')}",
                    f"lecture_title: {source.get('lecture_title', '')}",
                    f"lecture_id: {source.get('lecture_id', '')}",
                    f"lecture_number: {source.get('lecture_number', '')}",
                    f"title: {source.get('title', '')}",
                    f"source_url: {source.get('source_url', '')}",
                ]
            )
        )

    context = "\n\n---\n\n".join(context_lines)

    if not context:
        context = "PostgreSQL検索で該当するMOOCs情報は見つかりませんでした。"

    prompt = f"""
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

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
    )

    return response.text or ""
