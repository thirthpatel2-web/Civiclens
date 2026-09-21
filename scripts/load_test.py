"""Minimal concurrent load test against a running CivicLens server - no new dependency (uses the
app's own httpx). Not a substitute for a real load-testing tool (Locust/k6) at real scale, but a
genuine, runnable first check that the API holds up under modest concurrency before assuming it does.

Usage:
    python scripts/load_test.py --base-url http://localhost:8080 --token <bearer> \
        --path /api/v1/reference/directory --concurrency 20 --requests 200

On Windows Git Bash, prefix with MSYS_NO_PATHCONV=1 - otherwise Git Bash silently rewrites a
leading "/..." argument into a Windows filesystem path (e.g. "C:/Program Files/Git/api/...")
before Python ever sees it, and the request goes to the wrong place with no error.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from collections import Counter

import httpx


async def _one(client: httpx.AsyncClient, path: str) -> tuple[bool, int, float]:
    t0 = time.perf_counter()
    try:
        r = await client.get(path)
        return True, r.status_code, (time.perf_counter() - t0) * 1000
    except httpx.HTTPError:
        return False, 0, (time.perf_counter() - t0) * 1000


async def run(base_url: str, token: str | None, path: str, concurrency: int, total_requests: int) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    latencies: list[float] = []
    statuses: list[int] = []
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:

        async def bound() -> None:
            async with sem:
                _reached, status, ms = await _one(client, path)
                latencies.append(ms)
                statuses.append(status)

        t0 = time.perf_counter()
        await asyncio.gather(*(bound() for _ in range(total_requests)))
        elapsed = time.perf_counter() - t0

    latencies.sort()
    by_status = Counter(statuses)
    ok_count = by_status.get(200, 0)

    def pct(p: float) -> float:
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    print(f"{total_requests} requests, concurrency {concurrency}, against {base_url}{path}")
    print(f"  status codes: {dict(sorted(by_status.items()))}")
    print(f"  200 OK: {ok_count}/{total_requests} ({100 * ok_count / total_requests:.1f}%)")
    print(f"  wall time: {elapsed:.2f}s -> {total_requests / elapsed:.1f} req/s")
    print(f"  latency ms: min={latencies[0]:.0f} p50={pct(0.5):.0f} p95={pct(0.95):.0f} p99={pct(0.99):.0f} max={latencies[-1]:.0f} mean={statistics.mean(latencies):.0f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--token", default=None, help="Bearer token; omit to hit an unauthenticated path")
    ap.add_argument("--path", default="/")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--requests", type=int, default=100)
    args = ap.parse_args(argv)
    asyncio.run(run(args.base_url, args.token, args.path, args.concurrency, args.requests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
