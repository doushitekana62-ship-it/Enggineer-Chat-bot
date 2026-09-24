from typing import Any, Callable
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

# The chatbot can inspect every public table, but SQL execution remains read-only.
BLOCKED_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"VACUUM|ANALYZE|CALL|DO|COPY|EXECUTE|SET)\b",
    flags=re.IGNORECASE,
)


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

    def get_context(
        self,
        question: str,
        planner: Callable[[str, str], str] | None = None,
    ) -> dict[str, Any]:
        if config.DEMO_MODE:
            return self._demo_context(question)

        q = question.lower().strip()
        years = self._extract_years(question)
        project_type = self._extract_project_type(question)

        try:
            # Project queries are handled directly so simple questions do not wait for an LLM.
            if self._looks_like_project_question(q):
                if self._looks_like_count_question(q):
                    if years and project_type:
                        return self._count_projects_by_years(years, project_type)
                    if years:
                        return self._count_projects_by_years(years)

                project_no = self._extract_project_no(question)
                if project_no:
                    return self._project_detail(project_no)

                return self._project_list(
                    years=years,
                    project_type=project_type,
                )

            if self._contains_any(
                q,
                ["drawing", "gambar", "dwg", "dxf", "drafter", "drawing total"],
            ):
                if years or project_type:
                    return self._drawing_summary(years, project_type)
                return self._table_rows(
                    "drawinglist",
                    preferred_keywords=[
                        "project", "drawing", "dwg", "dxf", "name", "title",
                        "drafter", "status", "progress", "path"
                    ],
                    limit=100,
                    note="Data drawing dari drawinglist.",
                )

            if self._contains_any(
                q,
                ["karyawan", "pegawai", "employee", "member", "engineer", "staff"],
            ):
                return self._table_rows(
                    "member_list",
                    preferred_keywords=[
                        "name", "nama", "member", "employee", "nik",
                        "position", "jabatan", "department", "dept", "role"
                    ],
                    limit=200,
                    note="Data anggota/karyawan Engineering dari member_list.",
                )

            if self._contains_any(q, ["customer", "pelanggan", "client", "klien"]):
                return self._table_rows(
                    "customer_list",
                    preferred_keywords=[
                        "name", "nama", "customer", "company", "company_name",
                        "address", "alamat", "id"
                    ],
                    limit=200,
                    note="Data customer dari customer_list.",
                )

            if self._contains_any(
                q,
                ["statistik", "statistics", "statistic", "ringkasan", "summary", "dashboard", "rekap"],
            ):
                return self._statistics()

            # General questions use the real database schema as the LLM's tool surface.
            if planner:
                schema = self.schema_text()
                generated_sql = planner(question, schema)
                return self.execute_readonly(generated_sql, question)

            return {
                "source": "postgresql",
                "data": [],
                "note": "Pertanyaan memerlukan query dinamis. Schema database tersedia, tetapi SQL planner belum aktif.",
            }

        except Exception as exc:
            return {
                "source": "postgresql-error",
                "data": [],
                "note": f"Database query failed: {exc}",
            }

    def schema_text(self) -> str:
        tables = self._public_schema()
        lines: list[str] = []
        for table, columns in tables.items():
            lines.append(f"TABLE {table}:")
            lines.append("  " + ", ".join(columns))
        return "\n".join(lines)

    def execute_readonly(self, query: str, question: str = "") -> dict[str, Any]:
        cleaned = query.strip().rstrip(";").strip()
        if not cleaned:
            raise ValueError("SQL planner returned an empty query.")
        if ";" in cleaned:
            raise ValueError("Only one read-only SQL statement is allowed.")
        if BLOCKED_SQL.search(cleaned):
            raise ValueError("SQL planner produced a non-read-only statement.")
        if not re.match(r"^(SELECT|WITH)\b", cleaned, flags=re.IGNORECASE):
            raise ValueError("Only SELECT/WITH queries are allowed.")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(cleaned)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchmany(200)

        data = [
            {column: self._serialize_value(value) for column, value in zip(columns, row)}
            for row in rows
        ]

        return {
            "source": "postgresql",
            "data": data,
            "note": f"Read-only SQL generated for: {question}" if question else "Read-only SQL query.",
            "query": cleaned,
            "row_count": len(data),
        }

    def _public_schema(self) -> dict[str, list[str]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                    """
                )
                rows = cur.fetchall()

        schema: dict[str, list[str]] = {}
        for table, column in rows:
            schema.setdefault(table, []).append(column)
        return schema

    def _project_list(
        self,
        years: list[str] | None = None,
        project_type: str | None = None,
    ):
        conditions = []
        params: list[Any] = []

        if years:
            if len(years) == 1:
                conditions.append("SUBSTRING(project_no, 2, 4) = %s")
                params.append(years[0])
            else:
                conditions.append(
                    "SUBSTRING(project_no, 2, 4) BETWEEN %s AND %s"
                )
                params.extend([min(years), max(years)])

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
                    LIMIT 200
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
            "row_count": len(rows),
        }

    def _count_projects_by_years(
        self,
        years: list[str],
        project_type: str | None = None,
    ):
        conditions = ["project_no IS NOT NULL", "LENGTH(project_no) >= 5"]
        params: list[Any] = []

        if len(years) == 1:
            conditions.append("SUBSTRING(project_no, 2, 4) = %s")
            params.append(years[0])
        else:
            conditions.append("SUBSTRING(project_no, 2, 4) BETWEEN %s AND %s")
            params.extend([min(years), max(years)])

        if project_type:
            conditions.append("UPPER(SUBSTRING(project_no, 1, 1)) = %s")
            params.append(project_type)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT SUBSTRING(project_no, 2, 4) AS year,
                           COUNT(*) AS count
                    FROM projects
                    WHERE {' AND '.join(conditions)}
                    GROUP BY 1
                    ORDER BY 1
                    """,
                    params,
                )
                by_year = [
                    {"year": row[0], "count": row[1]}
                    for row in cur.fetchall()
                ]

        return {
            "source": "postgresql",
            "data": {
                "query": "project_count",
                "years": years,
                "project_type": project_type,
                "by_year": by_year,
                "total": sum(item["count"] for item in by_year),
            },
            "note": "Live database aggregate query.",
        }

    def _drawing_summary(
        self,
        years: list[str] | None,
        project_type: str | None,
    ):
        columns = self._table_columns("drawinglist")
        project_column = self._find_column(
            columns,
            [
                "project_no", "projectno", "project_number",
                "project", "no_project", "project_id"
            ],
        )

        if not project_column:
            return {
                "source": "postgresql",
                "data": [],
                "note": "drawinglist tidak memiliki kolom project yang dapat dipetakan otomatis.",
            }

        conditions = ["p.project_no IS NOT NULL"]
        params: list[Any] = []

        if years:
            if len(years) == 1:
                conditions.append("SUBSTRING(p.project_no, 2, 4) = %s")
                params.append(years[0])
            else:
                conditions.append(
                    "SUBSTRING(p.project_no, 2, 4) BETWEEN %s AND %s"
                )
                params.extend([min(years), max(years)])

        if project_type:
            conditions.append("UPPER(SUBSTRING(p.project_no, 1, 1)) = %s")
            params.append(project_type)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT COUNT(*) AS total_drawing,
                               COUNT(DISTINCT p.project_no) AS total_project
                        FROM drawinglist d
                        JOIN projects p
                          ON UPPER(CAST(d.{project_col} AS text))
                           = UPPER(p.project_no)
                        WHERE {conditions}
                        """
                    ).format(
                        project_col=sql.Identifier(project_column),
                        conditions=sql.SQL(" AND ").join(
                            sql.SQL(item) for item in conditions
                        ),
                    ),
                    params,
                )
                row = cur.fetchone()

        return {
            "source": "postgresql",
            "data": {
                "total_drawing": row[0],
                "total_project": row[1],
                "years": years or [],
                "project_type": project_type,
            },
            "note": "Total drawing dihitung dari drawinglist dan dipetakan ke projects.",
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

    def _table_rows(
        self,
        table: str,
        preferred_keywords: list[str],
        limit: int,
        note: str,
    ):
        columns = self._table_columns(table)
        if not columns:
            raise RuntimeError(f"Table {table} tidak ditemukan atau tidak memiliki kolom.")

        selected = [
            column for column in columns
            if any(keyword in column.lower() for keyword in preferred_keywords)
        ]
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

        return {
            "source": "postgresql",
            "data": [
                {
                    column: self._serialize_value(value)
                    for column, value in zip(selected, row)
                }
                for row in rows
            ],
            "note": note,
            "row_count": len(rows),
        }

    def _statistics(self):
        result: dict[str, Any] = {"projects": {}, "tables": {}}

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
                    GROUP BY 1 ORDER BY 1
                    """
                )
                result["projects"]["by_type"] = [
                    {"type": row[0], "count": row[1]} for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT SUBSTRING(project_no, 2, 4) AS year, COUNT(*)
                    FROM projects
                    WHERE project_no ~ '^.[0-9]{4}'
                    GROUP BY 1 ORDER BY 1 DESC LIMIT 20
                    """
                )
                result["projects"]["by_year"] = [
                    {"year": row[0], "count": row[1]} for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT COALESCE(status_project, 'UNKNOWN') AS status, COUNT(*)
                    FROM projects
                    GROUP BY 1 ORDER BY 2 DESC
                    """
                )
                result["projects"]["by_status"] = [
                    {"status": row[0], "count": row[1]} for row in cur.fetchall()
                ]

                for table in self._public_schema().keys():
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
        return self._public_schema().get(table, [])

    def _public_schema(self) -> dict[str, list[str]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                    """
                )
                rows = cur.fetchall()

        schema: dict[str, list[str]] = {}
        for table, column in rows:
            schema.setdefault(table, []).append(column)
        return schema

    @staticmethod
    def _find_column(columns: list[str], candidates: list[str]) -> str | None:
        lowered = {c.lower(): c for c in columns}
        for candidate in candidates:
            if candidate.lower() in lowered:
                return lowered[candidate.lower()]
        return None

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
            for word in ["berapa", "jumlah", "count", "total", "ada berapa", "banyak"]
        )

    @staticmethod
    def _extract_project_no(question: str) -> str | None:
        match = re.search(r"\b[NR]\d{7,}\b", question, flags=re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _extract_years(question: str) -> list[str]:
        return sorted(set(re.findall(r"\b(20\d{2})\b", question)))

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
        years = self._extract_years(question)
        project_type = self._extract_project_type(question)

        if years and project_type:
            count = sum(
                1
                for project in DEMO_PROJECTS
                if project["project_no"][0].upper() == project_type
                and project["project_no"][1:5] in years
            )
            return {
                "source": "demo",
                "data": {
                    "query": "project_count",
                    "years": years,
                    "project_type": project_type,
                    "count": count,
                },
                "note": "DEMO ONLY.",
            }

        return {
            "source": "demo",
            "data": DEMO_PROJECTS,
            "note": "DEMO ONLY.",
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
