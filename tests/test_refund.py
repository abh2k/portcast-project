def test_refund_success_and_idempotent(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    quota_service.consume(org_id, feature, units=70, request_id="req_refund")

    first = quota_service.refund(org_id, feature, units=70, request_id="req_refund")
    second = quota_service.refund(org_id, feature, units=70, request_id="req_refund")

    assert first.success is True
    assert first.reason == "refunded"
    assert second.success is True
    assert second.reason == "already_refunded"
    assert quota_service.usage(org_id, feature).used == 0


def test_refund_without_consume_is_rejected(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    result = quota_service.refund(org_id, feature, units=50, request_id="never_consumed")
    assert result.success is False
    assert result.reason == "consume_not_found"


def test_refund_units_mismatch_is_rejected(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=200)
    quota_service.consume(org_id, feature, units=50, request_id="mismatch_req")
    result = quota_service.refund(org_id, feature, units=40, request_id="mismatch_req")
    assert result.success is False
    assert result.reason == "refund_units_mismatch"
