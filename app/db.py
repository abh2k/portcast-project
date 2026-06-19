from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


@contextmanager
def get_db_conn() -> Generator[psycopg.Connection, None, None]:
    settings = get_settings()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def apply_schema(schema_path: Optional[str] = None) -> None:
    path = Path(schema_path or "schema.sql")
    sql = path.read_text(encoding="utf-8")
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
