"""Print a PII/secret-safe production readiness report."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from core.production_readiness import evaluate_production_readiness


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("self-hosted", "public-ga"), default="self-hosted")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    env = dict(os.environ)
    if args.env_file:
        env.update(_load_env_file(args.env_file))
    report = evaluate_production_readiness(
        env,
        profile=args.profile,
        path_exists=lambda value: Path(value).is_file(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["can_deploy"] else 1)


if __name__ == "__main__":
    main()
