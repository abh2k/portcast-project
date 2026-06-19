from pydantic import BaseModel, Field


class ConsumeRequest(BaseModel):
    org_id: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    units: int = Field(gt=0)
    request_id: str = Field(min_length=1)


class ConsumeResponse(BaseModel):
    allowed: bool
    reason: str


class RefundRequest(BaseModel):
    org_id: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    units: int = Field(gt=0)
    request_id: str = Field(min_length=1)


class RefundResponse(BaseModel):
    success: bool
    reason: str


class UsageResponse(BaseModel):
    org_id: str
    feature: str
    period: str
    limit: int
    used: int
    available: int
    reset_at: str
