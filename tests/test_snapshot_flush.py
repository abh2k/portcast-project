import uuid

from app.db import get_db_conn
from app.periods import current_period
from app.service.worker import snapshot_once


def test_snapshot_flush_is_overwrite_idempotent(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=500)
    period = current_period()
    idempotency_key = str(uuid.uuid4())

    quota_service.consume(org_id, feature, units=100, idempotency_key=idempotency_key)
    written_1 = snapshot_once()
    assert written_1 >= 1

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT used_units
                FROM monthly_usage
                WHERE org_id = %s AND feature = %s AND period = %s
                """,
                (org_id, feature, period),
            )
            row = cur.fetchone()
    assert row is not None
    assert row["used_units"] == 100

    written_2 = snapshot_once()
    assert written_2 >= 1
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT used_units
                FROM monthly_usage
                WHERE org_id = %s AND feature = %s AND period = %s
                """,
                (org_id, feature, period),
            )
            row = cur.fetchone()
    assert row["used_units"] == 100
