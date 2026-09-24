from typing import Any
import re

import psycopg2

from app import config

DEMO_PROJECTS = [
    {"project_no": "N2026001", "project_name": "Automation Line A", "status": "ACTIVE", "customer": "Demo Customer", "engineer": "Engineer A"},
    {"project_no": "N2026002", "project_name": "Conveyor System B", "status": "ACTIVE", "customer": "Demo Customer", "engineer": "Engineer B"},
    {"project_no": "R2026003", "project_name": "Revision Project C", "status": "ACTIVE", "customer": "Demo Customer", "engineer": "Engineer C"},
    {"project_no": "N2025004", "project_name": "Old New Project", "status": "COMPLETED", "customer": "Demo Customer", "engineer": "Engineer D"},
]


class DatabaseService:
    def status(self) -> dict[str, Any]:
        if config.DEMO_MODE:
            return {
                "connected": False,
                "mode": "demo",
                "message": "Live Engineering database is not connected. Prototype demo data is active.",
            }

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return {
                "connected": True,
                "mode": "postgresql",
                "message": "Engineering PostgreSQL database connected.",
            }
        except Exception as exc:
            return {
                "connected": False,
                "mode": "postgresql",
                "message": f"Database connection failed: {exc}",
            }

    def get_context(self, question: str) -> dict[str, Any]:
        if config.DEMO_MODE:
            return self._demo_context(question)

        year = self._extract_year(question)
        project_type = self._extract_project_type(question)

        if year and project_type:
            return self._count_projects_by_year_and_type(year, project_type)

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT project_no, project_name, status_project
                        FROM projects
                        ORDER BY project_no
                        LIMIT 100
                        """
                    )
                    rows = cur.fetchall()

            return {
                "source": "postgresql",
                "data": [
                    {"project_no": row[0], "project_name": row[1], "status": row[2]}
                    for row in rows
                ],
                "note": "Live database context.",
            }
        except Exception as exc:
            return {
                "source": "postgresql-error",
                "data": [],
                "note": f"Live database unavailable: {exc}",
            }

    def _count_projects_by_year_and_type(self, year: str, project_type: str):
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM projects
                        WHERE SUBSTRING(project_no, 2, 4) = %s
                          AND UPPER(SUBSTRING(project_no, 1, 1)) = %s
                        """,
                        (year, project_type),
                    )
                    count = cur.fetchone()[0]

            return {
                "source": "postgresql",
                "data": {
                    "query": "project_count",
                    "year": year,
                    "project_type": project_type,
                    "count": count,
                },
                "note": "Live database aggregate query.",
            }
        except Exception as exc:
            return {
                "source": "postgresql-error",
                "data": [],
                "note": f"Live database unavailable: {exc}",
            }

    def _demo_context(self, question: str):
        year = self._extract_year(question)
        project_type = self._extract_project_type(question)

        if year and project_type:
            count = sum(
                1
                for project in DEMO_PROJECTS
                if project["project_no"][0].upper() == project_type
                and project["project_no"][1:5] == year
            )
            return {
                "source": "demo",
                "data": {
                    "query": "project_count",
                    "year": year,
                    "project_type": project_type,
                    "count": count,
                },
                "note": "DEMO ONLY. Count is calculated from fictional prototype data.",
            }

        return {
            "source": "demo",
            "data": DEMO_PROJECTS,
            "note": "DEMO ONLY. Data is fictional and must not be presented as live company data.",
        }

    @staticmethod
    def _extract_year(question: str) -> str | None:
        match = re.search(r"\b(20\d{2})\b", question)
        return match.group(1) if match else None

    @staticmethod
    def _extract_project_type(question: str) -> str | None:
        match = re.search(
            r"\b(?:type|tipe)\s*[:=]?\s*([NR])\b|\btype\s+([NR])\b",
            question,
            flags=re.IGNORECASE,
        )
        if match:
            return (match.group(1) or match.group(2)).upper()

        if re.search(r"\bnew\b", question, flags=re.IGNORECASE):
            return "N"

        return None

    def _connect(self):
        if not all([config.DB_HOST, config.DB_NAME, config.DB_USER]):
            raise RuntimeError(
                "PostgreSQL configuration is incomplete. "
                "Set DB_HOST, DB_NAME and DB_USER in the application settings."
            )

        return psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            connect_timeout=config.DB_CONNECT_TIMEOUT,
        )
