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

    for source in sources:
        context_lines.append(
            "\n".join(
                [
                    f"course: {source.get('course', '')}",
                    f"title: {source.get('title', '')}",
                    f"deadline: {source.get('deadline', '')}",
                    f"content: {source.get('content') or ''}",
                ]
            )
        )

    context = "\n\n---\n\n".join(context_lines)

    if not context:
        context = "SQLite検索で該当する情報は見つかりませんでした。"

    prompt = f"""
以下のSQLite検索結果を参考に、質問へ日本語で回答してください。
検索結果に十分な情報がない場合は、その旨を簡潔に伝えてください。

質問:
{question}

検索結果:
{context}
"""

    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text or ""
