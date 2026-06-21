import uuid


def test_refund_success_and_idempotent(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    idempotency_key = str(uuid.uuid4())
    quota_service.consume(org_id, feature, units=70, idempotency_key=idempotency_key)

    first = quota_service.refund(idempotency_key=idempotency_key)
    second = quota_service.refund(idempotency_key=idempotency_key)

    assert first.success is True
    assert first.reason == "refunded"
    assert second.success is True
    assert second.reason == "already_refunded"
    assert quota_service.usage(org_id, feature).used == 0


def test_refund_without_consume_is_rejected(quota_service, make_quota):
    make_quota(monthly_limit=200)
    result = quota_service.refund(idempotency_key=str(uuid.uuid4()))
    assert result.success is False
    assert result.reason == "consume_not_found"


def test_refund_uses_original_consumed_units(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    idempotency_key = str(uuid.uuid4())
    quota_service.consume(org_id, feature, units=50, idempotency_key=idempotency_key)
    before = quota_service.usage(org_id, feature)
    result = quota_service.refund(idempotency_key=idempotency_key)
    after = quota_service.usage(org_id, feature)
    assert result.success is True
    assert result.reason == "refunded"
    assert before.used == 50
    assert after.used == 0


def test_refund_works_after_month_rollover_from_stored_metadata(quota_service, make_quota, monkeypatch):
    org_id, feature = make_quota(monthly_limit=200)
    idempotency_key = str(uuid.uuid4())

    monkeypatch.setattr("app.service.quota_service.current_period", lambda: "2026-06")
    quota_service.consume(org_id, feature, units=50, idempotency_key=idempotency_key)

    monkeypatch.setattr("app.service.quota_service.current_period", lambda: "2026-07")
    result = quota_service.refund(idempotency_key=idempotency_key)
    assert result.success is True
    assert result.reason == "refunded"
