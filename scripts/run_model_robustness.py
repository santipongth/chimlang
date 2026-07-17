"""Run an opt-in, low-cost Thai model robustness sample through the governed adapter."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from core.llm import BudgetGuard, CostEstimator, LLMAdapter, ModelTier, TierLoad
from core.llm.budget import release_budget_reservation, reserve_monthly_budget
from core.llm.userconfig import effective_llm_settings, effective_monthly_cap, effective_pricing
from core.run_manifest import canonical_hash
from core.text import sanitize_llm_text
from core.validation_store import ValidationStore

DEFAULT_MODELS = [
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.5-flash",
    "google/gemini-3.1-flash-lite-preview",
]

CASES = [
    {
        "case_id": "policy-urban",
        "domain": "policy",
        "persona": "คนทำงานในกรุงเทพฯ ที่เดินทางด้วยรถสาธารณะทุกวันและระวังค่าใช้จ่าย",
        "scenario": "เทศบาลจะลดค่าโดยสารรถไฟฟ้าร้อยละสิบ แต่ปรับภาษีท้องถิ่นขึ้นเล็กน้อย",
    },
    {
        "case_id": "policy-rural",
        "domain": "policy",
        "persona": "เกษตรกรต่างจังหวัดที่ใช้รถส่วนตัวและติดตามข่าวจากชุมชน",
        "scenario": "เทศบาลจะลดค่าโดยสารรถไฟฟ้าร้อยละสิบ แต่ปรับภาษีท้องถิ่นขึ้นเล็กน้อย",
    },
    {
        "case_id": "product-youth",
        "domain": "product",
        "persona": "นักศึกษาที่คุ้นเคยกับแอปใหม่ แต่กังวลเรื่องข้อมูลส่วนตัว",
        "scenario": "ธนาคารเปิดบริการยืนยันตัวตนด้วยใบหน้าเพื่อให้สมัครบัญชีได้เร็วขึ้น",
    },
    {
        "case_id": "product-older",
        "domain": "product",
        "persona": "ผู้สูงอายุที่ใช้สมาร์ตโฟนพื้นฐานและต้องการความช่วยเหลือเมื่อระบบผิดพลาด",
        "scenario": "ธนาคารเปิดบริการยืนยันตัวตนด้วยใบหน้าเพื่อให้สมัครบัญชีได้เร็วขึ้น",
    },
    {
        "case_id": "crisis-vendor",
        "domain": "crisis",
        "persona": "ผู้ค้าริมทางที่รายได้ขึ้นกับจำนวนคนผ่านพื้นที่",
        "scenario": "จังหวัดทดลองปิดถนนสายหลักในวันทำงานเพื่อลดฝุ่นเป็นเวลาหนึ่งเดือน",
    },
    {
        "case_id": "crisis-health",
        "domain": "crisis",
        "persona": "คนดูแลสมาชิกครอบครัวที่มีโรคทางเดินหายใจและติดตามค่าฝุ่นทุกวัน",
        "scenario": "จังหวัดทดลองปิดถนนสายหลักในวันทำงานเพื่อลดฝุ่นเป็นเวลาหนึ่งเดือน",
    },
]

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["stance", "confidence", "rationale"],
    "properties": {
        "stance": {"type": "string", "enum": ["support", "neutral", "oppose"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string", "minLength": 4, "maxLength": 600},
    },
}


def _thai_rationale(text: str) -> bool:
    has_thai = any("฀" <= char <= "๿" for char in text)
    has_cjk = any("一" <= char <= "鿿" for char in text)
    return has_thai and not has_cjk


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def _metrics(rows: list[dict], models: list[str], cases: list[dict]) -> dict:
    parsed = [row for row in rows if row.get("status") == "ok"]
    details = {}
    for model in models:
        model_rows = [row for row in rows if row["model"] == model]
        ok = [row for row in model_rows if row.get("status") == "ok"]
        latencies = [float(row["latency_s"]) for row in model_rows]
        details[model] = {
            "calls": len(model_rows),
            "parsed": len(ok),
            "parse_success_rate": len(ok) / len(model_rows) if model_rows else 0.0,
            "thai_rationale_rate": sum(bool(row.get("thai_rationale")) for row in ok) / len(ok)
            if ok
            else 0.0,
            "stance_distribution": {
                stance: sum(row.get("stance") == stance for row in ok)
                for stance in ("support", "neutral", "oppose")
            },
            "mean_confidence": statistics.fmean(float(row["confidence"]) for row in ok)
            if ok
            else None,
            "latency_p50_s": statistics.median(latencies) if latencies else None,
            "latency_p95_s": _percentile(latencies, 0.95),
            "input_tokens": sum(int(row.get("input_tokens") or 0) for row in model_rows),
            "output_tokens": sum(int(row.get("output_tokens") or 0) for row in model_rows),
            "cost_usd": sum(float(row.get("cost_usd") or 0) for row in model_rows),
        }
    matches = 0
    pairs = 0
    spreads = []
    for case in cases:
        values = [row for row in parsed if row["case_id"] == case["case_id"]]
        for left in range(len(values)):
            for right in range(left + 1, len(values)):
                pairs += 1
                matches += values[left]["stance"] == values[right]["stance"]
        confidences = [float(row["confidence"]) for row in values]
        if len(confidences) > 1:
            spreads.append(statistics.pstdev(confidences))
    expected = len(models) * len(cases)
    return {
        "models": models,
        "case_count": len(cases),
        "expected_calls": expected,
        "completed_calls": len(rows),
        "parsed_calls": len(parsed),
        "parse_success_rate": len(parsed) / expected if expected else 0.0,
        "thai_rationale_rate": sum(bool(row.get("thai_rationale")) for row in parsed) / len(parsed)
        if parsed
        else 0.0,
        "pairwise_stance_agreement": matches / pairs if pairs else None,
        "mean_confidence_dispersion": statistics.fmean(spreads) if spreads else None,
        "actual_cost_usd": sum(float(row.get("cost_usd") or 0) for row in rows),
        "models_detail": details,
    }


def run(models: list[str], sample_size: int, *, dry_run: bool, output: Path | None) -> dict:
    models = list(dict.fromkeys(model.strip() for model in models if model.strip()))
    if not 2 <= len(models) <= 3:
        raise ValueError("ต้องเลือก model ไม่ซ้ำ 2-3 รุ่น")
    cases = CASES[: max(1, min(sample_size, len(CASES)))]
    settings = effective_llm_settings()
    if "openrouter.ai" not in (settings.llm_base_url or "").lower():
        raise RuntimeError("robustness runner นี้ต้องใช้ OpenRouter ตามมติผู้ใช้")
    if not settings.llm_api_key:
        raise RuntimeError("ยังไม่มี OpenRouter API key")
    pricing = effective_pricing()
    estimate = CostEstimator(pricing).estimate(
        [TierLoad(model, len(cases), 600, 180) for model in models]
    )
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(estimate)
    configured_monthly_cap = effective_monthly_cap()
    monthly_cap = min(50.0, configured_monthly_cap) if configured_monthly_cap > 0 else 50.0
    run_id = "robustness-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    preflight = {
        "run_id": run_id,
        "models": models,
        "sample_size": len(cases),
        "estimated_usd": estimate.total_usd,
        "breakdown": estimate.breakdown,
        "run_cap_usd": settings.run_budget_usd_cap,
        "monthly_cap_usd": monthly_cap,
    }
    if dry_run:
        return {"preflight": preflight, "execution_started": False}

    reserve_monthly_budget(
        settings.postgres_url,
        {run_id: estimate.total_usd},
        monthly_cap,
        context="P9 model robustness opt-in",
    )
    rows: list[dict] = []
    try:
        for model in models:
            model_settings = settings.model_copy(
                update={"llm_model_crowd": model, "llm_model_analyst": model}
            )
            adapter = LLMAdapter(
                model_settings,
                pricing,
                guard,
                run_id=run_id,
                monthly_cap_usd=monthly_cap,
                monthly_reservation_id=run_id,
            )
            for case in cases:
                started = time.monotonic()
                base = {"model": model, "case_id": case["case_id"], "domain": case["domain"]}
                try:
                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "คุณเป็นผู้ตอบแบบจำลองในงานวิจัยภาษาไทย ตอบจากมุมมอง persona "
                                "โดยไม่อ้างว่าเป็นคนจริง ตอบภาษาไทยเท่านั้นใน rationale "
                                "ห้ามสร้างชื่อ บุคคล ที่อยู่ เบอร์โทร อีเมล หรือข้อมูลส่วนบุคคล"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "Persona: "
                                + case["persona"]
                                + chr(10)
                                + "สถานการณ์: "
                                + case["scenario"]
                                + chr(10)
                                + "เลือกท่าที support, neutral หรือ oppose พร้อม confidence 0-1 "
                                + "และเหตุผลภาษาไทยไม่เกินสองประโยค"
                            ),
                        },
                    ]
                    result = adapter.chat(
                        ModelTier.CROWD,
                        messages,
                        max_tokens=180,
                        temperature=0,
                        seed=20260717,
                        reasoning=False,
                        response_schema=RESPONSE_SCHEMA,
                        schema_name="thai_robustness_stance",
                    )
                    parsed = json.loads(sanitize_llm_text(result.text))
                    if parsed.get("stance") not in {"support", "neutral", "oppose"}:
                        raise ValueError("invalid stance")
                    confidence = float(parsed["confidence"])
                    if not 0 <= confidence <= 1:
                        raise ValueError("invalid confidence")
                    rationale = str(parsed.get("rationale") or "")
                    rows.append(
                        {
                            **base,
                            "status": "ok",
                            "stance": parsed["stance"],
                            "confidence": confidence,
                            "thai_rationale": _thai_rationale(rationale),
                            "latency_s": time.monotonic() - started,
                            "input_tokens": result.input_tokens,
                            "output_tokens": result.output_tokens,
                            "cost_usd": result.cost_usd,
                            "provider_model": result.model,
                            "structured_mode": result.structured_mode,
                        }
                    )
                except Exception as exc:
                    rows.append(
                        {
                            **base,
                            "status": "error",
                            "error_kind": type(exc).__name__,
                            "latency_s": time.monotonic() - started,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost_usd": 0.0,
                        }
                    )

        metrics = _metrics(rows, models, cases)
        complete = (
            metrics["completed_calls"] == metrics["expected_calls"]
            and metrics["parse_success_rate"] == 1.0
        )
        dataset_rows = []
        for case in cases:
            observed = {
                row["model"]: {
                    key: row.get(key)
                    for key in (
                        "status",
                        "stance",
                        "confidence",
                        "thai_rationale",
                        "latency_s",
                        "input_tokens",
                        "output_tokens",
                        "cost_usd",
                        "provider_model",
                        "structured_mode",
                        "error_kind",
                    )
                    if key in row
                }
                for row in rows
                if row["case_id"] == case["case_id"]
            }
            dataset_rows.append(
                {
                    "case_id": case["case_id"],
                    "prompt": case["scenario"],
                    "expected": {"ground_truth": None, "claim": "robustness_only"},
                    "observed": observed,
                    "slice": {"domain": case["domain"], "persona": case["persona"]},
                }
            )
        store = ValidationStore(settings.postgres_url)
        dataset = store.register_case_dataset(
            kind="model_robustness",
            name="P9 Thai model robustness sample",
            revision="p9-thai-robustness-v1",
            license_name="project-authored-synthetic-prompts",
            rows=dataset_rows,
            metadata={
                "models": models,
                "seed": 20260717,
                "temperature": 0,
                "user_opt_in": True,
                "no_human_ground_truth": True,
            },
            actor="codex-user-approved",
        )
        raw_hash = canonical_hash({"preflight": preflight, "rows": rows, "metrics": metrics})
        report = store.register_report(
            dataset["dataset_id"],
            kind="model_robustness",
            metrics=metrics,
            raw_result_hash=raw_hash,
            metadata={
                "benchmark_complete": complete,
                "method": "same Thai prompts/personas; stance agreement is not accuracy",
                "models": models,
                "pricing_snapshot": {
                    model: {
                        "input_usd_per_m": pricing.get(model).input_usd_per_m,
                        "output_usd_per_m": pricing.get(model).output_usd_per_m,
                    }
                    for model in models
                },
                "user_opt_in": True,
                "no_human_ground_truth": True,
                "run_id": run_id,
            },
            actor="codex-user-approved",
        )
        final = {
            "preflight": preflight,
            "execution_started": True,
            "benchmark_complete": complete,
            "dataset": dataset,
            "report": report,
        }
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        return final
    finally:
        release_budget_reservation(settings.postgres_url, run_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--sample-size", type=int, default=len(CASES))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.models, args.sample_size, dry_run=args.dry_run, output=args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("benchmark_complete", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
