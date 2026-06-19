# DESIGN

## Integration shape

This repository provides a FastAPI service exposing:

- `POST /quota/consume`
- `POST /quota/refund`
- `GET /quota/usage`

`QuotaService` is the core component used by API handlers and tests.

## Shared state and correctness model

Live quota state is in Redis under monthly namespaced keys:

- `quota:{org_id}:{feature}:{period}:state` (hash: `limit`, `used`)
- `quota:{org_id}:{feature}:{period}:consume:{request_id}`
- `quota:{org_id}:{feature}:{period}:refund:{request_id}`

Atomic correctness comes from Lua script execution (`EVALSHA`) in Redis:

- `consume.lua` performs idempotency check, quota check, then increments.
- `refund.lua` validates original consume, enforces refund idempotency, then decrements.

Because each script runs atomically, concurrent updates for the same key cannot over-serve or go negative.

## Batch policy

All-or-nothing: if a request asks for `N` units and fewer than `N` are available, request is rejected (`quota_exceeded`). Partial fulfillment is not supported.

## Failure and retry semantics

- **Client retries:** deduplicated via consume/refund idempotency keys keyed by `request_id`.
- **Downstream failure after consume:** caller invokes `refund` with same `request_id`.
- **Double refund attempts:** return `already_refunded`; no second decrement.
- **Redis unavailable:** fail closed with HTTP `503 quota_service_unavailable`.

## Reset and reporting

Period is UTC calendar month (`YYYY-MM`) derived at request time.

- Reset is implicit by key rollover to new month.
- `GET /quota/usage` returns current month from Redis with `reset_at`.
- Historical durability is handled by periodic snapshots in Postgres (`monthly_usage`).

## Durability and recovery

Postgres is used for:

- durable `quota_configs`
- periodic snapshots (`monthly_usage`)
- restoring Redis baseline on first access (lazy init)

Snapshot worker performs overwrite upsert (idempotent), not delta accumulation:

- `used_units = EXCLUDED.used_units`

If Redis is catastrophically lost, service can rebuild from latest Postgres snapshot, acknowledging loss window up to snapshot interval plus Redis AOF durability window.

## Real test evidence in this repo

Included tests prove:

- idempotent consume
- idempotent refund
- refund precondition checks
- no over-service under 1000 concurrent requests at quota 500
- snapshot overwrite idempotency

Run with:

```bash
pytest -q
```

## Scale-up path to 50k orgs

Current design is suitable for take-home and moderate production traffic. To scale further:

1. Redis HA with Sentinel/Cluster, careful slotting by org/feature.
2. Dedicated durable event log (Kafka) for billing-grade replay/audit.
3. Stronger reconciliation pipeline between Redis live state and durable ledger.
4. Isolate very hot org-feature keys (traffic shaping/admission control).
5. Multi-worker API replicas; keep scripts and key schema unchanged.
