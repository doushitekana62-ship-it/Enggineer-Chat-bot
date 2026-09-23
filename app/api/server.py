from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel

from app.database.service import DatabaseService
from app.ai.ollama import OllamaService
from app import config

app = FastAPI(
    title="Engineer Chat Bot",
    version="0.1.0-prototype",
    description="Prototype AI gateway for the Engineering application.",
)

db = DatabaseService()
ollama = OllamaService()


class ChatRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "application": "Engineer Chat Bot",
        "version": "0.1.0-prototype",
        "demo_mode": config.DEMO_MODE,
        "database": db.status(),
        "ollama": ollama.status(),
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    context = db.get_context(request.question)

    if not request.question.strip():
        return {"success": False, "error": "Question is empty."}

    try:
        answer = ollama.chat(request.question, context)
        return {
            "success": True,
            "answer": answer,
            "data_source": context.get("source"),
            "demo_mode": config.DEMO_MODE,
        }
    except Exception as exc:
        return {
            "success": False,
            "answer": None,
            "error": f"Ollama is unavailable: {exc}",
            "data_source": context.get("source"),
            "demo_mode": config.DEMO_MODE,
        }
