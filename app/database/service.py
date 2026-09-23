from typing import Any

import psycopg2

from app import config

DEMO_PROJECTS = [
    {
        "project_no": "DEMO-001",
        "project_name": "Automation Line A",
        "status": "ACTIVE",
        "customer": "Demo Customer",
        "engineer": "Engineer A",
    },
    {
        "project_no": "DEMO-002",
        "project_name": "Conveyor System B",
        "status": "ACTIVE",
        "customer": "Demo Customer",
        "engineer": "Engineer B",
    },
    {
        "project_no": "DEMO-003",
        "project_name": "Fixture Project C",
        "status": "COMPLETED",
        "customer": "Demo Customer",
        "engineer": "Engineer C",
    },
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
            return {
                "source": "demo",
                "data": DEMO_PROJECTS,
                "note": "DEMO ONLY. Data is fictional and must not be presented as live company data.",
            }

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT project_no, project_name, status
                        FROM projects
                        ORDER BY project_no
                        LIMIT 100
                        """
                    )
                    rows = cur.fetchall()

            return {
                "source": "postgresql",
                "data": [
                    {
                        "project_no": row[0],
                        "project_name": row[1],
                        "status": row[2],
                    }
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

    def _connect(self):
        if not all([config.DB_HOST, config.DB_NAME, config.DB_USER]):
            raise RuntimeError(
                "PostgreSQL configuration is incomplete. "
                "Set DB_HOST, DB_NAME and DB_USER in .env."
            )

        return psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            connect_timeout=config.DB_CONNECT_TIMEOUT,
        )
