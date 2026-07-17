"""Fail-closed startup gate for the supervised API + worker stack."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

REQUIRED = {"postgres", "redis", "worker", "neo4j"}


def wait(base_url: str, timeout_s: float, api_key: str = "") -> dict:
    deadline = time.monotonic() + timeout_s
    last_error = "not_started"
    headers = {"X-API-Key": api_key} if api_key else {}
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(base_url.rstrip("/") + "/health/deep", headers=headers)
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.load(response)
            components = payload.get("components") or {}
            if (
                payload.get("status") == "ok"
                and REQUIRED.issubset(components)
                and all(components[name] == "ok" for name in REQUIRED)
            ):
                return payload
            last_error = json.dumps(payload, ensure_ascii=False)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    raise RuntimeError(f"startup readiness ไม่ผ่านภายใน {timeout_s:.0f}s: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()
    print(json.dumps(wait(args.base_url, args.timeout, args.api_key), ensure_ascii=False))


if __name__ == "__main__":
    main()
