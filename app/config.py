import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    snapshot_interval_seconds: int
    idempotency_ttl_buffer_seconds: int


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/portcast",
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        snapshot_interval_seconds=int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "5")),
        idempotency_ttl_buffer_seconds=int(
            os.getenv("IDEMPOTENCY_TTL_BUFFER_SECONDS", str(7 * 24 * 60 * 60))
        ),
    )
