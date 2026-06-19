from app.periods import current_period


def test_consume_success_and_quota_exceeded(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=10)

    success = quota_service.consume(org_id, feature, units=6, request_id="req_1")
    assert success.allowed is True
    assert success.reason == "consumed"

    failed = quota_service.consume(org_id, feature, units=5, request_id="req_2")
    assert failed.allowed is False
    assert failed.reason == "quota_exceeded"

    usage = quota_service.usage(org_id, feature)
    assert usage.period == current_period()
    assert usage.used == 6
    assert usage.limit == 10
    assert usage.available == 4


def test_consume_is_idempotent(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=500)

    first = quota_service.consume(org_id, feature, units=50, request_id="same_req")
    second = quota_service.consume(org_id, feature, units=50, request_id="same_req")
    third = quota_service.consume(org_id, feature, units=50, request_id="same_req")

    assert first.allowed is True
    assert first.reason == "consumed"
    assert second.allowed is True
    assert second.reason == "already_consumed"
    assert third.allowed is True
    assert third.reason == "already_consumed"

    usage = quota_service.usage(org_id, feature)
    assert usage.used == 50
