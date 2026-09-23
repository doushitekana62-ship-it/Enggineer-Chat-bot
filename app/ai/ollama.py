from typing import Any
from datetime import datetime

import requests

from app import config


class OllamaError(RuntimeError):
    pass


class OllamaService:
    def status(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
            response.raise_for_status()
            models = [m.get("name") for m in response.json().get("models", [])]
            model_available = config.OLLAMA_MODEL in models or any(
                (m or "").split(":")[0] == config.OLLAMA_MODEL.split(":")[0] for m in models
            )
            return {
                "connected": True,
                "url": config.OLLAMA_URL,
                "model": config.OLLAMA_MODEL,
                "model_available": model_available,
                "models": models,
            }
        except Exception as exc:
            return {
                "connected": False,
                "url": config.OLLAMA_URL,
                "model": config.OLLAMA_MODEL,
                "model_available": False,
                "message": str(exc),
            }

    def chat(self, question: str, context: dict[str, Any]) -> str:
        if not question.strip():
            raise ValueError("Question is empty.")

        system = (
            "You are an internal Engineering data assistant. "
            "Answer only from the supplied context. "
            "If the context does not contain enough information, say so clearly. "
            "Never invent project, engineer, customer, drawing, PO, or schedule data. "
            "Do not claim access to the live company database unless the context says source=postgresql. "
            "Keep the answer concise and professional. Respond in the user's language."
        )

        prompt = (
            f"DATA SOURCE: {context.get('source')}\n"
            f"CONTEXT: {context.get('data')}\n"
            f"NOTE: {context.get('note', '')}\n\n"
            f"QUESTION: {question}"
        )

        try:
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
            data = response.json()
            answer = data.get("message", {}).get("content")
            if not answer:
                raise OllamaError("Ollama returned an empty response.")
            return answer.strip()
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama is unavailable: {exc}") from exc

    @staticmethod
    def metadata() -> dict[str, str]:
        return {
            "provider": "Ollama",
            "model": config.OLLAMA_MODEL,
            "prototype_time": datetime.now().isoformat(timespec="seconds"),
        }
