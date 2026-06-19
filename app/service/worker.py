import time

from app.config import get_settings
from app.db import get_db_conn
from app.periods import current_period
from app.redis_client import get_redis


def snapshot_once() -> int:
    redis_client = get_redis()
    period = current_period()
    pattern = f"quota:*:*:{period}:state"
    written = 0

    for key in redis_client.scan_iter(match=pattern):
        parts = key.split(":")
        if len(parts) != 5:
            continue

        _, org_id, feature, period_value, _ = parts
        data = redis_client.hgetall(key)
        limit = int(data.get("limit", 0))
        used = int(data.get("used", 0))

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO monthly_usage (
                        org_id,
                        feature,
                        period,
                        limit_units,
                        used_units,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (org_id, feature, period)
                    DO UPDATE SET
                        limit_units = EXCLUDED.limit_units,
                        used_units = EXCLUDED.used_units,
                        updated_at = now()
                    """,
                    (org_id, feature, period_value, limit, used),
                )
            conn.commit()
            written += 1

    return written


def run_forever() -> None:
    settings = get_settings()
    while True:
        try:
            snapshot_once()
        except Exception as exc:  # pragma: no cover - defensive worker loop
            print(f"snapshot worker error: {exc}")
        time.sleep(settings.snapshot_interval_seconds)


if __name__ == "__main__":
    run_forever()
