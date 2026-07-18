"""Unmocked Population -> Run -> Export workflow over real HTTP."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

import httpx


def _require(response: httpx.Response) -> dict:
    response.raise_for_status()
    return response.json()


def run(args: argparse.Namespace) -> dict:
    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    client = httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=30)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    result: dict = {"engine": args.engine, "started_at": stamp}
    run_id = ""
    try:
        health = _require(client.get("/health/deep"))
        if health.get("status") != "ok" or health.get("components", {}).get("worker") != "ok":
            raise RuntimeError(f"stack not ready: {health}")

        population_set = _require(
            client.post(
                "/population-sets",
                json={
                    "name": "Live acknowledged synthetic population",
                    "acknowledged_synthetic": True,
                },
            )
        )
        body = {
            "engine": args.engine,
            "subject": "ผลกระทบของต้นทุนพลังงานที่สูงขึ้นต่อครัวเรือนในเมือง",
            "domain": "เศรษฐกิจ",
            "agents": args.agents,
            "rounds": args.rounds,
            "population_set_id": population_set["set_id"],
        }
        if args.engine == "debate":
            body["sources"] = [
                {
                    "kind": "text",
                    "label": "หลักฐานทดสอบระบบจริง",
                    "text": "ราคาพลังงานที่สูงขึ้นอาจเพิ่มภาระการเดินทางและต้นทุนสินค้า",
                }
            ]
        readiness = _require(client.post("/runs/readiness", json=body))
        if not readiness["can_run"]:
            raise RuntimeError(f"run readiness blocked: {readiness}")
        estimate = float(readiness.get("cost", {}).get("estimated_usd") or 0)
        if estimate > args.max_estimate_usd:
            raise RuntimeError(
                f"estimated cost ${estimate:.6f} exceeds smoke cap ${args.max_estimate_usd:.6f}"
            )
        accepted_response = client.post(
            "/runs/async",
            headers={**headers, "Idempotency-Key": f"live-{stamp}-{args.engine}"},
            json=body,
        )
        if accepted_response.status_code != 202:
            raise RuntimeError(
                f"expected HTTP 202, got {accepted_response.status_code}: {accepted_response.text}"
            )
        accepted = accepted_response.json()
        run_id = accepted["run_id"]
        deadline = time.monotonic() + args.timeout
        detail = {}
        while time.monotonic() < deadline:
            detail = _require(client.get(f"/runs/{run_id}.json"))
            if detail["status"] in {"complete", "error", "canceled"}:
                break
            time.sleep(1)
        if detail.get("status") != "complete":
            raise RuntimeError(
                f"run did not complete: {detail.get('status')} {detail.get('progress_message')}"
            )
        manifest = _require(client.get(f"/runs/{run_id}/manifest"))
        population_governance = manifest.get("governance", {}).get("population_set", {})
        if not population_governance.get("hash_valid") or not population_governance.get(
            "acknowledged"
        ):
            raise RuntimeError("manifest lacks a valid acknowledged PopulationSetV1")
        export_response = client.get(f"/runs/{run_id}/export.json")
        export_response.raise_for_status()
        exported = export_response.json()
        watermark = exported.get("watermark") or {}
        snapshot = exported.get("snapshot") or {}
        if (
            snapshot.get("run_id") != run_id
            or watermark.get("run_id") != run_id
            or watermark.get("manifest_hash") != manifest["manifest_hash"]
        ):
            raise RuntimeError("stored export is missing run/manifest identity")
        result.update(
            {
                "status": "complete",
                "run_id": run_id,
                "population_set_id": population_set["set_id"],
                "estimated_usd": estimate,
                "actual_usd": float((detail.get("payload") or {}).get("cost_usd") or 0),
                "manifest_hash": manifest["manifest_hash"],
            }
        )
        return result
    finally:
        if args.cleanup_run and run_id:
            client.delete(f"/runs/{run_id}")
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--engine", choices=("fabric", "debate"), default="fabric")
    parser.add_argument("--agents", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--max-estimate-usd", type=float, default=0.05)
    parser.add_argument("--cleanup-run", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
