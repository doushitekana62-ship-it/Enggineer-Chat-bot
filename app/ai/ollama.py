from typing import Any
import requests
from app import config


class OllamaService:
    def status(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
            response.raise_for_status()
            models = [m.get("name") for m in response.json().get("models", [])]
            return {
                "connected": True,
                "url": config.OLLAMA_URL,
                "model": config.OLLAMA_MODEL,
                "models": models,
            }
        except Exception as exc:
            return {
                "connected": False,
                "url": config.OLLAMA_URL,
                "model": config.OLLAMA_MODEL,
                "message": str(exc),
            }

    def chat(self, question: str, context: dict[str, Any]) -> str:
        system = (
            "You are an internal Engineering data assistant. "
            "Answer only from the supplied context. "
            "If the context does not contain enough information, say so clearly. "
            "Do not invent company data. "
            "Keep answers concise and professional."
        )

        prompt = (
            f"{system}\n\n"
            f"DATA SOURCE: {context.get('source')}\n"
            f"CONTEXT:\n{context.get('data')}\n"
            f"NOTE: {context.get('note', '')}\n\n"
            f"QUESTION: {question}"
        )

        response = requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": 0.1},
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
