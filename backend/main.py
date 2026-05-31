from fastapi import FastAPI
from pydantic import BaseModel

from ai_module import generate_answer
from database import init_db
from search_backend import search

app = FastAPI()
init_db()


class AskRequest(BaseModel):
    question: str


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
