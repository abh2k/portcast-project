def test_refund_success_and_idempotent(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    quota_service.consume(org_id, feature, units=70, request_id="req_refund")

    first = quota_service.refund(org_id, feature, request_id="req_refund")
    second = quota_service.refund(org_id, feature, request_id="req_refund")

    assert first.success is True
    assert first.reason == "refunded"
    assert second.success is True
    assert second.reason == "already_refunded"
    assert quota_service.usage(org_id, feature).used == 0


def test_refund_without_consume_is_rejected(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    result = quota_service.refund(org_id, feature, request_id="never_consumed")
    assert result.success is False
    assert result.reason == "consume_not_found"


def test_refund_uses_original_consumed_units(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    quota_service.consume(org_id, feature, units=50, request_id="stored_units_req")
    before = quota_service.usage(org_id, feature)
    result = quota_service.refund(org_id, feature, request_id="stored_units_req")
    after = quota_service.usage(org_id, feature)
    assert result.success is True
    assert result.reason == "refunded"
    assert before.used == 50
    assert after.used == 0
