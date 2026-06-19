from dataclasses import dataclass


@dataclass
class ConsumeResult:
    allowed: bool
    reason: str


@dataclass
class RefundResult:
    success: bool
    reason: str


@dataclass
class UsageResult:
    org_id: str
    feature: str
    period: str
    limit: int
    used: int
    available: int
    reset_at: str
