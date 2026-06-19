from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from redis.exceptions import RedisError

from app.db import apply_schema
from app.schemas import (
    ConsumeRequest,
    ConsumeResponse,
    RefundRequest,
    RefundResponse,
    UsageResponse,
)
from app.service.quota_service import QuotaService

app = FastAPI(title="Portcast Quota Metering")


@lru_cache(maxsize=1)
def get_quota_service() -> QuotaService:
    return QuotaService()


@app.on_event("startup")
def startup() -> None:
    apply_schema()


@app.post("/quota/consume", response_model=ConsumeResponse)
def consume_quota(payload: ConsumeRequest) -> ConsumeResponse:
    try:
        result = get_quota_service().consume(
            org_id=payload.org_id,
            feature=payload.feature,
            units=payload.units,
            request_id=payload.request_id,
        )
        return ConsumeResponse(allowed=result.allowed, reason=result.reason)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="quota_service_unavailable") from exc


@app.post("/quota/refund", response_model=RefundResponse)
def refund_quota(payload: RefundRequest) -> RefundResponse:
    try:
        result = get_quota_service().refund(
            org_id=payload.org_id,
            feature=payload.feature,
            request_id=payload.request_id,
        )
        return RefundResponse(success=result.success, reason=result.reason)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="quota_service_unavailable") from exc


@app.get("/quota/usage", response_model=UsageResponse)
def get_usage(
    org_id: str = Query(min_length=1),
    feature: str = Query(min_length=1),
) -> UsageResponse:
    try:
        usage = get_quota_service().usage(org_id=org_id, feature=feature)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="quota_service_unavailable") from exc

    return UsageResponse(
        org_id=usage.org_id,
        feature=usage.feature,
        period=usage.period,
        limit=usage.limit,
        used=usage.used,
        available=usage.available,
        reset_at=usage.reset_at,
    )
