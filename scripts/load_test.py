import argparse
import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow direct execution: `python scripts/load_test.py`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import get_db_conn
from app.service.quota_service import QuotaService


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((p / 100.0) * (len(ordered) - 1))
    return ordered[idx]


def run_load(total_requests: int, workers: int, units: int, limit: int = None) -> dict:
    org_id = f"org_load_{uuid.uuid4().hex[:8]}"
    feature = "container_tracking"
    monthly_limit = limit if limit is not None else total_requests * units

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO quota_configs (org_id, feature, monthly_limit)
                VALUES (%s, %s, %s)
                ON CONFLICT (org_id, feature)
                DO UPDATE SET monthly_limit = EXCLUDED.monthly_limit, updated_at = now()
                """,
                (org_id, feature, monthly_limit),
            )
        conn.commit()

    service = QuotaService()
    latencies_ms = []
    start = time.perf_counter()

    def task(i):
        t0 = time.perf_counter()
        result = service.consume(org_id, feature, units=units, request_id=f"{org_id}_req_{i}")
        latency = (time.perf_counter() - t0) * 1000
        return result.allowed, latency

    allowed_count = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(task, i) for i in range(total_requests)]
        for fut in as_completed(futures):
            allowed, latency = fut.result()
            if allowed:
                allowed_count += 1
            latencies_ms.append(latency)

    elapsed = time.perf_counter() - start
    throughput = total_requests / elapsed if elapsed > 0 else 0

    return {
        "total_requests": total_requests,
        "workers": workers,
        "units_per_request": units,
        "monthly_limit": monthly_limit,
        "total_demand_units": total_requests * units,
        "allowed": allowed_count,
        "rejected": total_requests - allowed_count,
        "elapsed_seconds": round(elapsed, 4),
        "throughput_rps": round(throughput, 2),
        "p50_ms": round(statistics.median(latencies_ms), 3),
        "p95_ms": round(percentile(latencies_ms, 95), 3),
        "p99_ms": round(percentile(latencies_ms, 99), 3),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run quota metering load test.")
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=100)
    parser.add_argument("--units", type=int, default=1)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Monthly quota limit for test org/feature. Defaults to requests*units.",
    )
    args = parser.parse_args()

    metrics = run_load(args.requests, args.workers, args.units, args.limit)
    for key, value in metrics.items():
        print(f"{key}: {value}")
