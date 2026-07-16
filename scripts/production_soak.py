"""Exercise the deployed API/worker path with concurrent zero-cost Fabric runs.

This runner is intentionally external to the application process. It verifies the
real HTTP, PostgreSQL, Redis, Celery, heartbeat/event, and read-after-write path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from dataclasses import asdict, dataclass

import httpx

TERMINAL_OK = {"complete", "success"}
TERMINAL_ERROR = {"error", "failure", "failed", "canceled", "cancelled", "revoked"}


@dataclass
class Trial:
    index: int
    job_id: str = ""
    run_id: str = ""
    status: str = "not_started"
    queue_seconds: float = 0.0
    total_seconds: float = 0.0
    event_count: int = 0
    heartbeat_seen: bool = False
    error: str = ""


def percentile(values: list[float], quantile: float) -> float:
    """Return a linearly interpolated percentile without a statistics dependency."""

    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(trials: list[Trial]) -> dict:
    passed = [trial for trial in trials if trial.status in TERMINAL_OK and not trial.error]
    failed = [trial for trial in trials if trial not in passed]
    return {
        "requested": len(trials),
        "passed": len(passed),
        "failed": len(failed),
        "p50_total_seconds": round(percentile([item.total_seconds for item in passed], 0.5), 3),
        "p95_total_seconds": round(percentile([item.total_seconds for item in passed], 0.95), 3),
        "heartbeat_coverage": round(
            sum(item.heartbeat_seen for item in passed) / max(1, len(passed)), 3
        ),
        "event_coverage": round(
            sum(item.event_count > 0 for item in passed) / max(1, len(passed)), 3
        ),
        "failures": [asdict(item) for item in failed],
    }


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key} if api_key else {}


async def execute_trial(
    client: httpx.AsyncClient,
    index: int,
    *,
    agents: int,
    timeout_seconds: float,
    poll_seconds: float,
    cleanup: bool,
) -> Trial:
    trial = Trial(index=index)
    started = time.monotonic()
    try:
        response = await client.post(
            "/runs/async",
            json={
                "engine": "fabric",
                "subject": f"production soak {index}",
                "domain": "operations",
                "agents": agents,
                "rounds": 1,
                "retrieval_mode": "bm25",
                "seed": 20260716 + index,
            },
        )
        response.raise_for_status()
        queued = response.json()
        trial.job_id = str(queued["job_id"])
        trial.run_id = str(queued.get("run_id", ""))
        trial.status = str(queued.get("status", "queued")).lower()
        trial.queue_seconds = time.monotonic() - started

        deadline = started + timeout_seconds
        while time.monotonic() < deadline:
            response = await client.get(f"/run-jobs/{trial.job_id}")
            response.raise_for_status()
            state = response.json()
            trial.status = str(state.get("status", "unknown")).lower()
            trial.run_id = str(state.get("run_id") or trial.run_id)
            trial.heartbeat_seen = trial.heartbeat_seen or bool(state.get("heartbeat_at"))
            if trial.status in TERMINAL_OK:
                break
            if trial.status in TERMINAL_ERROR:
                trial.error = str(
                    state.get("error") or state.get("progress_message") or trial.status
                )
                break
            await asyncio.sleep(poll_seconds)
        else:
            trial.status = "timeout"
            trial.error = f"no terminal state within {timeout_seconds:.0f}s"

        if trial.status in TERMINAL_OK and trial.run_id:
            detail_response = await client.get(f"/runs/{trial.run_id}.json")
            detail_response.raise_for_status()
            detail = detail_response.json()
            events = detail.get("events") or []
            event_ids = [event.get("id") for event in events]
            if any(event_id is None for event_id in event_ids) or len(event_ids) != len(
                set(event_ids)
            ):
                trial.error = "run events contain missing or duplicate ids"
            trial.event_count = len(events)
            trial.heartbeat_seen = trial.heartbeat_seen or bool(detail.get("heartbeat_at"))
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        trial.status = "client_error"
        trial.error = f"{type(exc).__name__}: {exc}"
    finally:
        trial.total_seconds = time.monotonic() - started
        if cleanup and trial.run_id:
            try:
                await client.delete(f"/runs/{trial.run_id}")
            except httpx.HTTPError:
                pass
    return trial


async def run_soak(args: argparse.Namespace) -> tuple[list[Trial], dict]:
    limits = httpx.Limits(max_connections=args.concurrency * 2, max_keepalive_connections=20)
    timeout = httpx.Timeout(30.0, connect=10.0)
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        headers=_headers(args.api_key),
        limits=limits,
        timeout=timeout,
    ) as client:

        async def bounded(index: int) -> Trial:
            async with semaphore:
                return await execute_trial(
                    client,
                    index,
                    agents=args.agents,
                    timeout_seconds=args.timeout,
                    poll_seconds=args.poll,
                    cleanup=args.cleanup,
                )

        trials = await asyncio.gather(*(bounded(index) for index in range(1, args.runs + 1)))
    return trials, summarize(trials)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--base-url", default="http://127.0.0.1:8000")
    result.add_argument("--api-key", default="")
    result.add_argument("--runs", type=int, default=20)
    result.add_argument("--concurrency", type=int, default=5)
    result.add_argument("--agents", type=int, default=100)
    result.add_argument("--timeout", type=float, default=180.0)
    result.add_argument("--poll", type=float, default=0.5)
    result.add_argument("--cleanup", action=argparse.BooleanOptionalAction, default=True)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.runs < 20:
        raise SystemExit("production soak requires --runs >= 20")
    if args.concurrency < 2:
        raise SystemExit("production soak requires --concurrency >= 2")
    trials, report = asyncio.run(run_soak(args))
    print(json.dumps({"summary": report, "trials": [asdict(item) for item in trials]}, indent=2))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
