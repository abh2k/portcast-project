from pathlib import Path
from typing import Optional

from redis import Redis

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
    def request_meta_key(request_id: str) -> str:
        return f"quota:request:{request_id}:meta"

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
        request_id: str,
    ) -> ConsumeResult:
        period = current_period()
        if not self._ensure_state_initialized(org_id, feature, period):
            return ConsumeResult(allowed=False, reason="quota_not_configured")

        result = self.redis.evalsha(
            self.consume_sha,
            2,
            self.state_key(org_id, feature, period),
            self.request_meta_key(request_id),
            units,
            self._request_metadata_ttl(),
            org_id,
            feature,
            period,
        )
        return ConsumeResult(allowed=self._bool_from_lua(result[0]), reason=str(result[1]))

    def _resolve_request_metadata(self, request_id: str) -> Optional[dict]:
        data = self.redis.hgetall(self.request_meta_key(request_id))
        if not data:
            return None
        if "org_id" not in data or "feature" not in data or "period" not in data:
            return None
        return data

    def refund(self, request_id: str) -> RefundResult:
        metadata = self._resolve_request_metadata(request_id)
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
            self.request_meta_key(request_id),
            self._request_metadata_ttl(),
        )
        return RefundResult(success=self._bool_from_lua(result[0]), reason=str(result[1]))

    def usage(self, org_id: str, feature: str) -> UsageResult:
        period = current_period()
        if not self._ensure_state_initialized(org_id, feature, period):
            raise ValueError("quota_not_configured")

        data = self.redis.hgetall(self.state_key(org_id, feature, period))
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
