# Portcast Quota Metering

FastAPI + Redis Lua quota metering service for per-org, per-feature monthly limits.

![Quota Management Service](Quota_management_service.png)

## Quick start

```bash
docker compose up --build
```

Service URL: `http://localhost:8080`

## API

### Consume quota

```bash
curl -X POST http://localhost:8080/quota/consume \
  -H "Content-Type: application/json" \
  -d '{
    "org_id":"org_123",
    "feature":"container_tracking",
    "units":50,
    "request_id":"req_abc"
  }'
```

### Refund quota

```bash
curl -X POST http://localhost:8080/quota/refund \
  -H "Content-Type: application/json" \
  -d '{
    "request_id":"req_abc"
  }'
```

Refund resolves `org_id`, `feature`, `period`, and `units` from consume-time metadata stored against `request_id`.

### Current usage

```bash
curl "http://localhost:8080/quota/usage?org_id=org_123&feature=container_tracking"
```

## Tests

Start dependencies:

```bash
docker compose up -d postgres redis
python apply_migrations.py
```

Install Python dependencies (local venv):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run tests:

```bash
pytest -q
```

## Load test

```bash
python scripts/load_test.py --requests 2000 --workers 100 --units 1
```

To force rejections (oversubscribe demand vs limit):

```bash
python scripts/load_test.py --requests 2000 --workers 100 --units 100 --limit 150000
```

Sample output fields:

- `throughput_rps`
- `p50_ms`
- `p95_ms`
- `p99_ms`
- `allowed`
- `rejected`

Record your own numbers from your machine and include them in your submission notes.

## Files

- `app/service/quota_service.py` - core consume/refund/usage logic
- `app/lua/consume.lua` - atomic consume script
- `app/lua/refund.lua` - atomic refund script
- `app/service/worker.py` - snapshot flush worker
- `DESIGN.md` - design decisions and tradeoffs