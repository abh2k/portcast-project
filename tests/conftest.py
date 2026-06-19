import uuid

import psycopg
import pytest
from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings
from app.db import apply_schema, get_db_conn
from app.service.quota_service import QuotaService


@pytest.fixture(scope="session", autouse=True)
def ensure_schema() -> None:
    try:
        apply_schema()
    except psycopg.Error as exc:
        pytest.skip(f"Postgres unavailable for integration tests: {exc}")


@pytest.fixture()
def redis_client() -> Redis:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        client.ping()
    except RedisError as exc:
        pytest.skip(f"Redis unavailable for integration tests: {exc}")
    # Test isolation: request_id ledger keys persist with TTL, so clear between tests.
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture()
def db_ready() -> None:
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except psycopg.Error as exc:
        pytest.skip(f"Postgres unavailable for integration tests: {exc}")


@pytest.fixture()
def quota_service(redis_client: Redis, db_ready: None) -> QuotaService:
    return QuotaService(redis_client=redis_client)


@pytest.fixture()
def make_quota(redis_client: Redis, db_ready: None):
    def _make(monthly_limit: int = 500, feature: str = "container_tracking") -> tuple[str, str]:
        org_id = f"org_test_{uuid.uuid4().hex[:8]}"
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO quota_configs (org_id, feature, monthly_limit)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (org_id, feature)
                    DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit, updated_at = now()
                    """,
                    (org_id, feature, monthly_limit),
                )
            conn.commit()
        return org_id, feature

    return _make
