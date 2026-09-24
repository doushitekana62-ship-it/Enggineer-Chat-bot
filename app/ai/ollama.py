from typing import Any
from datetime import datetime
import json

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
                (m or "").split(":")[0] == config.OLLAMA_MODEL.split(":")[0]
                for m in models
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

    def plan_sql(self, question: str, schema: str) -> str:
        if not question.strip():
            raise ValueError("Question is empty.")

        system = (
            "You are the SQL planner for an internal Engineering PostgreSQL database. "
            "Use ONLY the tables, columns, primary keys and foreign-key relationships in the supplied schema. "
            "Return JSON only: {\"sql\":\"SELECT ...\"}. "
            "The SQL MUST be read-only and contain exactly one SELECT or WITH query. "
            "Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, "
            "REVOKE, COPY, CALL, DO, SET or multiple statements. "
            "Use LIMIT 200 for row lists. "
            "Prefer exact columns instead of SELECT *. "
            "Project type is encoded by the first character of projects.project_no: "
            "N=New and R=Repair/Revision. "
            "Project year is characters 2-5 of projects.project_no. "
            "For activity/history questions, inspect the schema for the actual activity/log/history table and its date/timestamp column; do not invent a table or column. "
            "For 'hari ini', use CURRENT_DATE or CURRENT_DATE-compatible timestamp filtering. "
            "Use JOINs only when supported by declared foreign keys or clearly matching project identifiers. "
            "If the question cannot be answered from the schema, return {\"sql\":\"SELECT 1 WHERE FALSE\"}."
        )

        prompt = (
            f"SCHEMA:\n{schema}\n\n"
            f"QUESTION:\n{question}\n\n"
            "Return JSON only."
        )

        data = self._request(
            system=system,
            prompt=prompt,
            timeout=30,
            num_predict=192,
            json_mode=True,
        )
        raw = data.get("message", {}).get("content", "")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama SQL planner returned invalid JSON.") from exc

        query = str(parsed.get("sql", "")).strip()
        if not query:
            raise OllamaError("Ollama SQL planner returned no SQL.")
        return query

    def chat(self, question: str, context: dict[str, Any]) -> str:
        if not question.strip():
            raise ValueError("Question is empty.")

        system = (
            "You are an internal Engineering data assistant. "
            "Answer only from the supplied PostgreSQL context. "
            "Do not invent project, employee, customer, drawing, purchase, schedule, "
            "or statistic data. If data is empty, say that the requested data was not found. "
            "For numeric questions, use the exact numbers in the context. "
            "For project lists, project_no is the project identifier and project_name is the actual project name. "
            "If the user asks for nama project, return project_name and optionally project_no; never use project_no as the name. "
            "For lists, preserve names and project numbers exactly from the context. "
            "Do not mention SQL unless the user asks. "
            "Answer naturally in Indonesian and keep simple answers concise."
        )

        # Keep the final prompt small. SQL/result rows are already filtered by the database.
        compact_data = context.get("data")
        if isinstance(compact_data, list):
            compact_data = compact_data[:200]

        prompt = (
            f"DATA SOURCE: {context.get('source')}\n"
            f"DATA: {compact_data}\n"
            f"NOTE: {context.get('note', '')}\n"
            f"QUESTION: {question}"
        )

        data = self._request(
            system=system,
            prompt=prompt,
            timeout=45,
            num_predict=256,
            json_mode=False,
        )
        answer = data.get("message", {}).get("content")
        if not answer:
            raise OllamaError("Ollama returned an empty response.")
        return answer.strip()

    def _request(
        self,
        system: str,
        prompt: str,
        timeout: int,
        num_predict: int,
        json_mode: bool,
    ) -> dict[str, Any]:
        try:
            payload = {
                "model": config.OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "options": {
                    "temperature": 0.0,
                    "num_predict": num_predict,
                    "num_ctx": 2048,
                },
                "keep_alive": "10m",
            }
            if json_mode:
                payload["format"] = "json"

            response = requests.post(
                f"{config.OLLAMA_URL}/api/chat",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise OllamaError(
                "Ollama membutuhkan waktu terlalu lama. "
                "Query database sudah dipisahkan dari proses AI; coba pertanyaan yang lebih spesifik."
            ) from exc
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama is unavailable: {exc}") from exc

    @staticmethod
    def metadata() -> dict[str, str]:
        return {
            "provider": "Ollama",
            "model": config.OLLAMA_MODEL,
            "prototype_time": datetime.now().isoformat(timespec="seconds"),
        }
