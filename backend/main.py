from fastapi import FastAPI
from pydantic import BaseModel
from database import init_db
from search_backend import search
from ai_module import mock_ai_answer

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
            "error": "質問を入力してください。"
        }

    sources = search(question)
    answer = mock_ai_answer(question, sources)

    return {
        "answer": answer,
        "sources": sources,
        "error": None
    }
