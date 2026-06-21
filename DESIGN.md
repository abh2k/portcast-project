# DESIGN

High-level design for the quota management service.

![Quota Management Service](Quota_management_service.png)

## Integration shape

This service exposes:

- `POST /quota/consume`
- `POST /quota/refund`
- `GET /quota/usage`

`QuotaService` contains the main quota logic used by API handlers and tests.

## Run locally

Start the full stack:

```bash
docker compose up --build --scale app=3
```

Service URL: `http://localhost:8080` (nginx load balancer in front of app replicas).

## API quick examples

Consume:

```bash
curl -X POST http://localhost:8080/quota/consume \
  -H "Content-Type: application/json" \
  -d '{"org_id":"org_123","feature":"container_tracking","units":50,"idempotency_key":"key_abc"}'
```

Refund:

```bash
curl -X POST http://localhost:8080/quota/refund \
  -H "Content-Type: application/json" \
  -d '{"idempotency_key":"key_abc"}'
```

Usage:

```bash
curl "http://localhost:8080/quota/usage?org_id=org_123&feature=container_tracking"
```

## Shared state and correctness model

Redis has two key types:

1. `quota:{org_id}:{feature}:{period}:state`
   - `limit`
   - `used`

2. `quota:idempotency:{idempotency_key}:meta`
   - `org_id`
   - `feature`
   - `period`
   - `units`
   - `status`

Simple view:
- `state` key = live counters for one org-feature-month
- `meta` key = request history for idempotency + refund

All app instances are stateless and share the same Redis/Postgres state, so scaling app replicas does not split quota state.

TTL:
- state key TTL: `seconds_until_period_end + 7 days`
- request metadata TTL: `1 hour`

Correctness guarantee:
- Redis Lua scripts are atomic.
- `consume.lua` checks idempotency, checks quota, then increments `used`.
- `refund.lua` reads request metadata, decrements `used`, then marks request as refunded; if called again with the same `idempotency_key`, it returns `already_refunded` (idempotent behavior).
- Under concurrency, quota cannot go below zero or be over-served for successful operations.

## Batch policy

All-or-nothing.
If request asks for `N` units and available is `< N`, request is rejected (`quota_exceeded`).

## Failure and retry handling

Core rule:
- Same logical operation retry -> same `idempotency_key`
- New logical operation attempt -> new `idempotency_key`

In this implementation, the gateway sends the same `idempotency_key` directly to quota APIs (`consume`/`refund`).

Case 1: Client times out, but downstream may still succeed
- Client sends key `K1`
- Gateway calls `consume(K1)` and quota is deducted once
- Client times out and retries with same key `K1`
- `consume(K1)` returns `already_consumed`, so quota is not deducted again
- Gateway returns stored success if available, or keeps operation in-progress and retries downstream with same `K1`

Case 2: Downstream transient failure
- `consume(K1)` succeeds
- Downstream temporarily fails/timeouts
- Gateway retries downstream with the same `K1`
- No immediate refund is done for transient failures
- Quota remains reserved for that same logical operation

Case 3: Downstream terminal failure
- `consume(K1)` succeeds
- Downstream retries are exhausted (terminal failure)
- Gateway calls `refund(K1)` exactly once
- Gateway marks `K1` as terminal failed/refunded
- If client retries with same `K1`, gateway returns the same terminal failure and does not call `consume` again
- A new user attempt must send a new key, e.g. `K2`

State machine (K1):
- `NEW -> CONSUMED/IN_PROGRESS -> SUCCEEDED`
- `NEW -> CONSUMED/IN_PROGRESS -> TERMINAL_FAILED -> REFUNDED`

Behavior by state:
- Same `K1` while `IN_PROGRESS`: do not consume again
- Same `K1` after `SUCCEEDED`: return same success/result
- Same `K1` after `REFUNDED`: return same failure, do not consume again
- New attempt after failure requires new key (`K2`)

If Redis is unavailable, service fails closed (`503 quota_service_unavailable`).

## Reset and reporting

Period model is UTC calendar month (`YYYY-MM`).

- Monthly reset is automatic by moving to a new period key.
- If the new period key is missing in Redis, the service initializes it from SQL (`quota_configs.monthly_limit` and `monthly_usage.used_units`, defaulting used to `0`) and then continues on Redis.
- `GET /quota/usage` reads Redis for current period.
- If Redis key is missing, usage falls back to SQL (`quota_configs` + `monthly_usage`).
- Postgres snapshots are used for durability and historical reporting.

## Durability and recovery

Postgres stores:
- durable quota config (`quota_configs`)
- periodic usage snapshots (`monthly_usage`)
- baseline for Redis rebuild if needed

Snapshot worker writes overwrite values (idempotent), not deltas:
- `used_units = EXCLUDED.used_units`

If Redis is lost, service can rebuild from latest Postgres snapshot.
Limitation: recent unsnapshotted usage may be missing.

## Real test evidence

Tests cover:
- idempotent consume
- idempotent refund
- refund edge cases
- high-contention correctness (1000 concurrent consume calls, limit 500)
- snapshot overwrite idempotency

Run:

```bash
pytest -q
```

## Real load-test numbers

This load test sends many concurrent consume requests to one org/feature.
It measures throughput + latency and checks allowed/rejected behavior under oversubscription.

Command:

```bash
.venv/bin/python scripts/load_test.py --requests 2000 --workers 100 --units 100 --limit 150000
```

Output:

```text
total_requests: 2000
workers: 100
units_per_request: 100
monthly_limit: 150000
total_demand_units: 200000
allowed: 1500
rejected: 500
elapsed_seconds: 0.2934
throughput_rps: 6815.74
p50_ms: 5.784
p95_ms: 17.591
p99_ms: 47.679
```

## Scale-up path to 50k orgs

To support 50k orgs:

1. Use Redis Cluster and shard by `org_id`.
2. Pre-create next-month Redis keys before rollover.
3. Strengthen reconciliation between Redis and Postgres snapshot history.
4. Add protection for hot keys (rate limit / queue / traffic shaping).
5. Run multiple app replicas behind a load balancer.
6. Add fast config sync/invalidation for `quota_configs` changes.
7. Pre-warm in small batches (for example 1k keys per batch).
8. Use clear scaling signals (p95 latency, Redis CPU/memory, Lua errors, snapshot lag) for autoscaling.

## What we rejected

1. SQL-only request path.  
   Rejected because it is harder to meet low-latency target and high concurrency.

2. Redis-only without SQL snapshots.  
   Rejected because recovery after Redis failure would be weak.

3. Reserve/commit/refund 3-endpoint flow.  
   Rejected because success path needs extra API call (`reserve` then `commit`).

4. Redis-only usage reads with no SQL fallback.  
   Rejected because usage should still be available when Redis key is missing.

## Where the system falls over

1. Snapshot lag window.  
   Recent usage can be lost if Redis fails before next snapshot flush.

2. Redis AOF durability window (`appendfsync everysec`).  
   Up to ~1 second of writes can be lost on hard crash.

3. Request metadata memory pressure.  
   High request rate can increase Redis memory from `meta` keys (even with 1-hour TTL).

4. Hot-key serialization.  
   One very hot `(org_id, feature, period)` key can bottleneck even with sharding.

## AI Assistance Disclosure

AI was used for:
- reviewing edge cases
- improving test coverage ideas
- documentation wording and formating
- speed up the implementation process
- Creating the load test script

Own design decisions:
- Using redis for atomic consume/refund
- all-or-nothing batch behavior
- monthly calendar reset
- Idempotency loop in retries
- Postgres snapshot strategy

All the design decisions were taken by me, I used AI to speed up the implementation. I reviewed all the outputs that the AI generated.
