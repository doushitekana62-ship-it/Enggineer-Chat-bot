from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app import config
from app.ai.ollama import OllamaService
from app.database.service import DatabaseService

app = FastAPI(
    title="Engineer Chat Bot",
    version="0.2.0-prototype",
    description="Read-only AI gateway for the Engineering PostgreSQL database.",
)

db = DatabaseService()
ollama = OllamaService()


class ChatRequest(BaseModel):
    question: str


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Engineer Chat Bot",
        "version": "0.2.0-prototype",
        "message": "Prototype is running.",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "application": "Engineer Chat Bot",
        "version": "0.2.0-prototype",
        "demo_mode": config.DEMO_MODE,
        "database": db.status(),
        "ollama": ollama.status(),
    }


@app.get("/schema")
def schema() -> dict[str, Any]:
    if config.DEMO_MODE:
        return {"source": "demo", "schema": "DEMO MODE"}
    return {"source": "postgresql", "schema": db.schema_text()}


@app.post("/query")
def query(request: ChatRequest) -> dict[str, Any]:
    question = request.question.strip()
    if not question:
        return {"success": False, "error": "Question is empty."}

    try:
        context = db.get_context(question, planner=ollama.plan_sql)
        return {
            "success": True,
            "data_source": context.get("source"),
            "context": context,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "data_source": "error",
        }


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    question = request.question.strip()
    if not question:
        return {"success": False, "error": "Question is empty."}

    try:
        context = db.get_context(question, planner=ollama.plan_sql)
        answer = ollama.chat(question, context)
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
            "error": str(exc),
            "data_source": "error",
            "demo_mode": config.DEMO_MODE,
        }
