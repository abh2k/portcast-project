from concurrent.futures import ThreadPoolExecutor


def test_hot_key_contention_never_overserves(quota_service, make_quota):
    org_id, feature = make_quota(monthly_limit=500)

    def consume_once(i: int) -> bool:
        result = quota_service.consume(
            org_id=org_id,
            feature=feature,
            units=1,
            request_id=f"req_{i}",
        )
        return result.allowed

    with ThreadPoolExecutor(max_workers=100) as pool:
        allowed = list(pool.map(consume_once, range(1000)))

    success_count = sum(1 for item in allowed if item)
    rejected_count = len(allowed) - success_count

    usage = quota_service.usage(org_id, feature)
    assert success_count == 500
    assert rejected_count == 500
    assert usage.used == 500
    assert usage.available == 0
