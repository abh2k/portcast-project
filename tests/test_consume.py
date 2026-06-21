import uuid

from app.periods import current_period


def test_consume_success_and_quota_exceeded(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=10)
    request_id_1 = str(uuid.uuid4())
    request_id_2 = str(uuid.uuid4())

    success = quota_service.consume(org_id, feature, units=6, request_id=request_id_1)
    assert success.allowed is True
    assert success.reason == "consumed"

    failed = quota_service.consume(org_id, feature, units=5, request_id=request_id_2)
    assert failed.allowed is False
    assert failed.reason == "quota_exceeded"

    usage = quota_service.usage(org_id, feature)
    assert usage.period == current_period()
    assert usage.used == 6
    assert usage.limit == 10
    assert usage.available == 4


def test_consume_is_idempotent(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=500)
    request_id = str(uuid.uuid4())

    first = quota_service.consume(org_id, feature, units=50, request_id=request_id)
    second = quota_service.consume(org_id, feature, units=50, request_id=request_id)
    third = quota_service.consume(org_id, feature, units=50, request_id=request_id)

    assert first.allowed is True
    assert first.reason == "consumed"
    assert second.allowed is True
    assert second.reason == "already_consumed"
    assert third.allowed is True
    assert third.reason == "already_consumed"

    usage = quota_service.usage(org_id, feature)
    assert usage.used == 50


def test_same_request_id_is_idempotent_even_if_reused(quota_service, make_quota):
    org_a, feature_a = make_quota(monthly_limit=500, feature="container_tracking")
    org_b, feature_b = make_quota(monthly_limit=500, feature="sailing_schedule")
    request_id = str(uuid.uuid4())

    first = quota_service.consume(org_a, feature_a, units=10, request_id=request_id)
    second = quota_service.consume(org_b, feature_b, units=10, request_id=request_id)

    assert first.allowed is True
    assert first.reason == "consumed"
    assert second.allowed is True
    assert second.reason == "already_consumed"
    assert quota_service.usage(org_a, feature_a).used == 10
    assert quota_service.usage(org_b, feature_b).used == 0
