from pathlib import Path
from typing import Optional

from redis import Redis
from redis.exceptions import RedisError

from app.config import get_settings
from app.db import get_db_conn
from app.models import ConsumeResult, RefundResult, UsageResult
from app.periods import current_period, reset_at_iso, ttl_seconds_until_reset_with_buffer
from app.redis_client import get_redis, load_lua_script


LUA_DIR = Path(__file__).resolve().parent.parent / "lua"


class QuotaService:
    def __init__(self, redis_client: Optional[Redis] = None) -> None:
        self.settings = get_settings()
        self.redis = redis_client or get_redis()
        self.consume_sha = load_lua_script(self.redis, str(LUA_DIR / "consume.lua"))
        self.refund_sha = load_lua_script(self.redis, str(LUA_DIR / "refund.lua"))

    @staticmethod
    def state_key(org_id: str, feature: str, period: str) -> str:
        return f"quota:{org_id}:{feature}:{period}:state"

    @staticmethod
    def idempotency_meta_key(idempotency_key: str) -> str:
        return f"quota:idempotency:{idempotency_key}:meta"

    def _state_ttl(self) -> int:
        return ttl_seconds_until_reset_with_buffer(self.settings.state_ttl_buffer_seconds)

    def _request_metadata_ttl(self) -> int:
        return self.settings.request_metadata_ttl_seconds

    @staticmethod
    def _bool_from_lua(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return int(value) == 1
        if isinstance(value, str):
            return value == "1"
        return False

    def _ensure_state_initialized(self, org_id: str, feature: str, period: str) -> bool:
        key = self.state_key(org_id, feature, period)
        if self.redis.exists(key):
            return True

        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT monthly_limit
                    FROM quota_configs
                    WHERE org_id = %s AND feature = %s
                    """,
                    (org_id, feature),
                )
                quota_row = cur.fetchone()
                if not quota_row:
                    return False

                cur.execute(
                    """
                    SELECT used_units
                    FROM monthly_usage
                    WHERE org_id = %s AND feature = %s AND period = %s
                    """,
                    (org_id, feature, period),
                )
                usage_row = cur.fetchone()

        used_units = int(usage_row["used_units"]) if usage_row else 0
        limit = int(quota_row["monthly_limit"])
        ttl = self._state_ttl()

        # Keep state creation race-safe across multiple service instances.
        self.redis.hsetnx(key, "limit", limit)
        self.redis.hsetnx(key, "used", used_units)
        self.redis.expire(key, ttl)
        return True

    def consume(
        self,
        org_id: str,
        feature: str,
        units: int,
        idempotency_key: str,
    ) -> ConsumeResult:
        period = current_period()
        if not self._ensure_state_initialized(org_id, feature, period):
            return ConsumeResult(allowed=False, reason="quota_not_configured")

        result = self.redis.evalsha(
            self.consume_sha,
            2,
            self.state_key(org_id, feature, period),
            self.idempotency_meta_key(idempotency_key),
            units,
            self._request_metadata_ttl(),
            org_id,
            feature,
            period,
        )
        return ConsumeResult(allowed=self._bool_from_lua(result[0]), reason=str(result[1]))

    def _resolve_idempotency_metadata(self, idempotency_key: str) -> Optional[dict]:
        data = self.redis.hgetall(self.idempotency_meta_key(idempotency_key))
        if not data:
            return None
        if "org_id" not in data or "feature" not in data or "period" not in data:
            return None
        return data

    def refund(self, idempotency_key: str) -> RefundResult:
        metadata = self._resolve_idempotency_metadata(idempotency_key)
        if not metadata:
            return RefundResult(success=False, reason="consume_not_found")

        org_id = metadata["org_id"]
        feature = metadata["feature"]
        period = metadata["period"]

        if not self._ensure_state_initialized(org_id, feature, period):
            return RefundResult(success=False, reason="quota_not_configured")

        result = self.redis.evalsha(
            self.refund_sha,
            2,
            self.state_key(org_id, feature, period),
            self.idempotency_meta_key(idempotency_key),
            self._request_metadata_ttl(),
        )
        return RefundResult(success=self._bool_from_lua(result[0]), reason=str(result[1]))

    def usage(self, org_id: str, feature: str) -> UsageResult:
        period = current_period()
        key = self.state_key(org_id, feature, period)
        try:
            data = self.redis.hgetall(key)
        except RedisError:
            data = {}

        # Primary path: return live Redis value when key exists.
        if data:
            limit = int(data.get("limit", 0))
            used = int(data.get("used", 0))
            return UsageResult(
                org_id=org_id,
                feature=feature,
                period=period,
                limit=limit,
                used=used,
                available=max(limit - used, 0),
                reset_at=reset_at_iso(),
            )

        # Fallback path: derive usage from SQL when Redis key is absent.
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT monthly_limit
                    FROM quota_configs
                    WHERE org_id = %s AND feature = %s
                    """,
                    (org_id, feature),
                )
                quota_row = cur.fetchone()
                if not quota_row:
                    raise ValueError("quota_not_configured")

                cur.execute(
                    """
                    SELECT used_units
                    FROM monthly_usage
                    WHERE org_id = %s AND feature = %s AND period = %s
                    """,
                    (org_id, feature, period),
                )
                usage_row = cur.fetchone()

        limit = int(quota_row["monthly_limit"])
        used = int(usage_row["used_units"]) if usage_row else 0
        return UsageResult(
            org_id=org_id,
            feature=feature,
            period=period,
            limit=limit,
            used=used,
            available=max(limit - used, 0),
            reset_at=reset_at_iso(),
        )
