"""Deterministic experiment expansion, comparison, and sensitivity analysis."""

from __future__ import annotations

from itertools import product

from api.models import RunBody
from core.config import get_settings
from core.llm.budget import MonthlyBudgetExceededError, spent_this_month
from core.run_quality import estimate_run_cost
from core.runstore import RunStore
from simulation.engines import get_engine

ALLOWED_SWEEP_FIELDS = {
    "seed",
    "agents",
    "rounds",
    "red_team",
    "retrieval_mode",
    "reflection",
}
MAX_SWEEP_VARIANTS = 12


def expand_sweep(base: RunBody, parameters: dict[str, list]) -> list[tuple[RunBody, dict]]:
    unknown = set(parameters) - ALLOWED_SWEEP_FIELDS
    if unknown:
        raise ValueError(f"parameter ที่ไม่รองรับ: {', '.join(sorted(unknown))}")
    invalid_values = any(
        not isinstance(values, list) or not values for values in parameters.values()
    )
    if not parameters or invalid_values:
        raise ValueError("parameter sweep ต้องมี list ที่ไม่ว่างอย่างน้อยหนึ่งมิติ")
    keys = sorted(parameters)
    combinations = list(product(*(parameters[key] for key in keys)))
    if len(combinations) > MAX_SWEEP_VARIANTS:
        raise ValueError(f"sweep จำกัด {MAX_SWEEP_VARIANTS} variants ต่อ workspace")
    variants: list[tuple[RunBody, dict]] = []
    for values in combinations:
        variant = dict(zip(keys, values, strict=True))
        body = RunBody(**{**base.model_dump(), **variant})
        engine = get_engine(body.engine)
        if body.agents > engine.max_agents:
            raise ValueError(f"agents ของ variant เกิน cap {engine.max_agents}")
        if body.engine == "fabric":
            if body.red_team:
                raise ValueError("fabric experiment ไม่รับ red_team flag; ใช้ Compare workflow แยก")
            ignored = {"rounds", "red_team", "retrieval_mode", "reflection"} & set(parameters)
            if ignored:
                raise ValueError(
                    "fabric sweep รองรับเฉพาะ seed/agents; มิติเหล่านี้ไม่มีผลจริง: "
                    + ", ".join(sorted(ignored))
                )
        if body.engine == "debate" and body.red_team and body.agents + 2 > engine.max_agents:
            raise ValueError("debate red_team ต้องเหลือที่ให้ adversarial agents 2 ตัวภายใน cap")
        variants.append((body, variant))
    return variants


def preflight_sweep(variants: list[tuple[RunBody, dict]], monthly_cap: float) -> dict:
    estimates = [estimate_run_cost(body.model_dump()) for body, _ in variants]
    for estimate in estimates:
        if estimate.get("error"):
            raise ValueError(str(estimate["error"]))
        if float(estimate.get("estimated_usd", 0)) > float(estimate.get("run_cap_usd", 0)):
            raise ValueError("มี variant เกินเพดานต้นทุนต่อ run")
    total = sum(float(item.get("estimated_usd", 0)) for item in estimates)
    dsn = get_settings().postgres_url
    spent = spent_this_month(dsn) if total > 0 else 0.0
    if monthly_cap > 0 and spent + total > monthly_cap:
        raise MonthlyBudgetExceededError(spent, monthly_cap)
    return {
        "variants": len(variants),
        "estimated_usd": round(total, 6),
        "variant_estimates_usd": [
            round(float(item.get("estimated_usd", 0)), 6) for item in estimates
        ],
        "monthly_spent_usd": round(spent, 6),
        "monthly_cap_usd": monthly_cap,
    }


def extract_result_value(detail: dict) -> float | None:
    if detail.get("status") != "complete" or not detail.get("payload"):
        return None
    payload = detail["payload"]
    if detail.get("engine") == "debate":
        values = (payload.get("metrics") or {}).get("per_round_avg_stance") or []
        return float(values[-1]) if values else None
    headline = (payload.get("brief") or {}).get("headline_range") or []
    if len(headline) == 2:
        return (float(headline[0]) + float(headline[1])) / 2
    return None


def analyze_workspace(dsn: str, workspace: dict) -> dict:
    store = RunStore(dsn)
    rows: list[dict] = []
    for member in workspace.get("members", []):
        try:
            detail = store.get(member["run_id"])
            rows.append(
                {
                    "run_id": member["run_id"],
                    "variant": member.get("variant") or {},
                    "engine": detail["engine"],
                    "status": detail["status"],
                    "value": extract_result_value(detail),
                    "cost_usd": float((detail.get("payload") or {}).get("cost_usd", 0) or 0),
                    "error": detail.get("error"),
                }
            )
        except ValueError:
            rows.append(
                {
                    "run_id": member["run_id"],
                    "variant": member.get("variant") or {},
                    "engine": "unknown",
                    "status": "deleted",
                    "value": None,
                    "cost_usd": 0.0,
                    "error": "operational_run_deleted",
                }
            )
    dimensions: dict[str, dict] = {}
    keys = sorted({key for row in rows for key in row["variant"]})
    for key in keys:
        groups: dict[str, list[float]] = {}
        for row in rows:
            if row["value"] is None or key not in row["variant"]:
                continue
            label = str(row["variant"][key])
            groups.setdefault(label, []).append(float(row["value"]))
        group_rows = [
            {
                "value": label,
                "n": len(values),
                "mean": round(sum(values) / len(values), 6),
                "min": round(min(values), 6),
                "max": round(max(values), 6),
            }
            for label, values in sorted(groups.items())
        ]
        means = [row["mean"] for row in group_rows]
        dimensions[key] = {
            "groups": group_rows,
            "sensitivity_range": round(max(means) - min(means), 6) if len(means) > 1 else None,
        }
    ranked = sorted(
        (
            {"parameter": key, "sensitivity_range": value["sensitivity_range"]}
            for key, value in dimensions.items()
            if value["sensitivity_range"] is not None
        ),
        key=lambda item: (-item["sensitivity_range"], item["parameter"]),
    )
    return {
        "runs": rows,
        "completed": sum(row["status"] == "complete" for row in rows),
        "failed": sum(row["status"] in {"error", "deleted", "canceled"} for row in rows),
        "total_cost_usd": round(sum(row["cost_usd"] for row in rows), 6),
        "dimensions": dimensions,
        "ranked_sensitivity": ranked,
        "public_votes_used": False,
        "note": (
            "mechanical comparison from stored run snapshots; public votes never feed the engine"
        ),
    }
