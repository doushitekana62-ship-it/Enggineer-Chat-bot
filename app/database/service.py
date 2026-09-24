from typing import Any
import re

import psycopg2
from psycopg2 import sql

from app import config

DEMO_PROJECTS = [
    {"project_no": "N2026001", "project_name": "Automation Line A", "status": "ACTIVE", "customer": "Demo Customer", "engineer": "Engineer A"},
    {"project_no": "N2026002", "project_name": "Conveyor System B", "status": "ACTIVE", "customer": "Demo Customer", "engineer": "Engineer B"},
    {"project_no": "R2026003", "project_name": "Revision Project C", "status": "ACTIVE", "customer": "Demo Customer", "engineer": "Engineer C"},
    {"project_no": "N2025004", "project_name": "Old New Project", "status": "COMPLETED", "customer": "Demo Customer", "engineer": "Engineer D"},
]

ALLOWED_TABLES = {
    "projects",
    "member_list",
    "customer_list",
    "drawinglist",
    "project_status",
}


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

        q = question.lower().strip()
        year = self._extract_year(question)
        project_type = self._extract_project_type(question)

        try:
            # Project-specific questions
            if self._looks_like_project_question(q):
                if year and project_type and self._looks_like_count_question(q):
                    return self._count_projects_by_year_and_type(year, project_type)

                project_no = self._extract_project_no(question)
                if project_no:
                    return self._project_detail(project_no)

                return self._project_list(year=year, project_type=project_type)

            # Employee / member questions
            if self._contains_any(q, ["karyawan", "pegawai", "employee", "member", "engineer", "engineer list"]):
                return self._table_rows(
                    "member_list",
                    preferred_keywords=[
                        "name", "nama", "member", "employee", "nik",
                        "position", "jabatan", "department", "dept", "role"
                    ],
                    limit=100,
                    note="Data anggota/karyawan Engineering dari member_list.",
                )

            # Customer questions
            if self._contains_any(q, ["customer", "pelanggan", "client", "klien"]):
                return self._table_rows(
                    "customer_list",
                    preferred_keywords=[
                        "name", "nama", "customer", "company", "company_name",
                        "address", "alamat", "id"
                    ],
                    limit=100,
                    note="Data customer dari customer_list.",
                )

            # Drawing questions
            if self._contains_any(q, ["drawing", "gambar", "dwg", "dxf", "drafter"]):
                return self._table_rows(
                    "drawinglist",
                    preferred_keywords=[
                        "project", "drawing", "dwg", "dxf", "name", "nama",
                        "drafter", "status", "progress", "path"
                    ],
                    limit=100,
                    note="Data drawing dari drawinglist.",
                )

            # General statistics / dashboard-style questions
            if self._contains_any(q, ["statistik", "statistics", "statistic", "ringkasan", "summary", "dashboard", "rekap"]):
                return self._statistics()

            # Generic project listing as a useful fallback
            return self._project_list(year=year, project_type=project_type)

        except Exception as exc:
            return {
                "source": "postgresql-error",
                "data": [],
                "note": f"Database query failed: {exc}",
            }

    def _project_list(self, year: str | None = None, project_type: str | None = None):
        conditions = []
        params: list[Any] = []

        if year:
            conditions.append("SUBSTRING(project_no, 2, 4) = %s")
            params.append(year)

        if project_type:
            conditions.append("UPPER(SUBSTRING(project_no, 1, 1)) = %s")
            params.append(project_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT project_no, project_name, customer, status_project,
                           delivery_date, pic_mechanic, pic_electric
                    FROM projects
                    {where_clause}
                    ORDER BY project_no
                    LIMIT 100
                    """,
                    params,
                )
                rows = cur.fetchall()

        return {
            "source": "postgresql",
            "data": [
                {
                    "project_no": row[0],
                    "project_name": row[1],
                    "customer": row[2],
                    "status_project": row[3],
                    "delivery_date": row[4].isoformat() if row[4] else None,
                    "pic_mechanic": row[5],
                    "pic_electric": row[6],
                }
                for row in rows
            ],
            "note": "Live project data from PostgreSQL.",
        }

    def _project_detail(self, project_no: str):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT project_no, project_name, customer, machine_capacity,
                           machine_type, delivery_date, original_project,
                           reference_project, status_project, pic_mechanic,
                           pic_electric, furnace_type, heat_source,
                           processed_material, id_customer, pic_me_id,
                           pic_elc_id, id, machine_type_id,
                           machine_capacity_unit_id, project_status_id,
                           process_material_id, file_3d_path
                    FROM projects
                    WHERE UPPER(project_no) = UPPER(%s)
                    LIMIT 1
                    """,
                    (project_no,),
                )
                row = cur.fetchone()

        if not row:
            return {
                "source": "postgresql",
                "data": [],
                "note": f"Project {project_no} tidak ditemukan.",
            }

        columns = [
            "project_no", "project_name", "customer", "machine_capacity",
            "machine_type", "delivery_date", "original_project",
            "reference_project", "status_project", "pic_mechanic",
            "pic_electric", "furnace_type", "heat_source",
            "processed_material", "id_customer", "pic_me_id",
            "pic_elc_id", "id", "machine_type_id",
            "machine_capacity_unit_id", "project_status_id",
            "process_material_id", "file_3d_path"
        ]

        data = dict(zip(columns, row))
        if data.get("delivery_date"):
            data["delivery_date"] = data["delivery_date"].isoformat()

        return {
            "source": "postgresql",
            "data": data,
            "note": f"Detail project {project_no} dari PostgreSQL.",
        }

    def _count_projects_by_year_and_type(self, year: str, project_type: str):
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

    def _table_rows(
        self,
        table: str,
        preferred_keywords: list[str],
        limit: int,
        note: str,
    ):
        if table not in ALLOWED_TABLES:
            raise ValueError("Table is not allowed.")

        columns = self._table_columns(table)
        if not columns:
            raise RuntimeError(f"Table {table} tidak ditemukan atau tidak memiliki kolom.")

        selected = [
            column for column in columns
            if any(keyword in column.lower() for keyword in preferred_keywords)
        ]

        # If keyword matching is too narrow, use the first few non-sensitive-looking columns.
        if not selected:
            selected = columns[:8]

        selected = selected[:12]

        with self._connect() as conn:
            with conn.cursor() as cur:
                query = sql.SQL("SELECT {} FROM {} LIMIT %s").format(
                    sql.SQL(", ").join(sql.Identifier(c) for c in selected),
                    sql.Identifier(table),
                )
                cur.execute(query, (limit,))
                rows = cur.fetchall()

        data = [
            {
                column: self._serialize_value(value)
                for column, value in zip(selected, row)
            }
            for row in rows
        ]

        return {
            "source": "postgresql",
            "data": data,
            "note": note,
        }

    def _statistics(self):
        result: dict[str, Any] = {
            "projects": {},
            "tables": {},
        }

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM projects")
                result["projects"]["total"] = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT UPPER(SUBSTRING(project_no, 1, 1)) AS project_type,
                           COUNT(*)
                    FROM projects
                    WHERE project_no IS NOT NULL AND LENGTH(project_no) >= 5
                    GROUP BY 1
                    ORDER BY 1
                    """
                )
                result["projects"]["by_type"] = [
                    {"type": row[0], "count": row[1]} for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT SUBSTRING(project_no, 2, 4) AS year,
                           COUNT(*)
                    FROM projects
                    WHERE project_no ~ '^.[0-9]{4}'
                    GROUP BY 1
                    ORDER BY 1 DESC
                    LIMIT 20
                    """
                )
                result["projects"]["by_year"] = [
                    {"year": row[0], "count": row[1]} for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT COALESCE(status_project, 'UNKNOWN') AS status,
                           COUNT(*)
                    FROM projects
                    GROUP BY 1
                    ORDER BY 2 DESC
                    """
                )
                result["projects"]["by_status"] = [
                    {"status": row[0], "count": row[1]} for row in cur.fetchall()
                ]

                for table in ["member_list", "customer_list", "drawinglist", "project_status"]:
                    try:
                        cur.execute(
                            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
                        )
                        result["tables"][table] = cur.fetchone()[0]
                    except Exception:
                        conn.rollback()
                        result["tables"][table] = None

        return {
            "source": "postgresql",
            "data": result,
            "note": "Ringkasan statistik yang dihitung langsung dari database Engineering.",
        }

    def _table_columns(self, table: str) -> list[str]:
        if table not in ALLOWED_TABLES:
            return []

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table,),
                )
                return [row[0] for row in cur.fetchall()]

    @staticmethod
    def _serialize_value(value: Any):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    @staticmethod
    def _contains_any(question: str, words: list[str]) -> bool:
        return any(word in question for word in words)

    @staticmethod
    def _looks_like_project_question(question: str) -> bool:
        return any(
            word in question
            for word in ["project", "proyek", "nama project", "project no", "nomor project"]
        )

    @staticmethod
    def _looks_like_count_question(question: str) -> bool:
        return any(
            word in question
            for word in ["berapa", "jumlah", "count", "total", "ada berapa"]
        )

    @staticmethod
    def _extract_project_no(question: str) -> str | None:
        match = re.search(r"\b[NR]\d{7,}\b", question, flags=re.IGNORECASE)
        return match.group(0).upper() if match else None

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

        if re.search(r"\brepair\b|\brevisi\b|\brevision\b", question, flags=re.IGNORECASE):
            return "R"

        return None

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
