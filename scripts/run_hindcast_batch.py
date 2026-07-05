"""Hindcast batch — วัด exit criteria Phase 0: "hindcast ภายในผ่าน ≥ 3/5 เหตุการณ์"

    uv run python scripts/run_hindcast_batch.py --agents 5

ทุกเหตุการณ์รันใต้ hindcast prompt (leak-tested ใน M1) — external retrieval ปิดโดยสถาปัตยกรรม
scenario เลือกตั้ง/การเมือง: aggregate เท่านั้น ป้าย simulation_estimate (GOV-02)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from governance.election import ElectionPolicy, classify_scenario
from trust.hindcast import load_event
from trust.hindcast.predictor import event_passes, load_truth, predict_event

ROOT = Path(__file__).resolve().parents[1]
PASS_REQUIRED = 3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-dir", default="data/samples/hindcast")
    parser.add_argument("--agents", type=int, default=5, help="agents ต่อ target (≤ cap)")
    args = parser.parse_args()

    settings = get_settings()
    if args.agents > settings.max_agents_per_run:
        raise SystemExit(
            f"agents ต่อ target ({args.agents}) เกิน cap ช่วง dev ({settings.max_agents_per_run})"
        )

    event_dirs = sorted(
        d for d in Path(args.events_dir).iterdir() if d.is_dir() and (d / "meta.yaml").exists()
    )
    events = [(d, load_event(d), load_truth(d)) for d in event_dirs]
    total_targets = sum(len(e.prediction_targets) for _, e, _ in events)

    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    estimate = CostEstimator(pricing).estimate(
        [
            TierLoad(
                settings.llm_model_crowd,
                calls=total_targets * args.agents,
                avg_input_tokens=15000,
                avg_output_tokens=300,
            )
        ]
    )
    guard.check_estimate(estimate)
    print(
        f"เหตุการณ์: {len(events)} | targets: {total_targets} | agents/target: {args.agents} "
        f"| estimate ${estimate.total_usd:.4f} (cap ${settings.run_budget_usd_cap:.2f})"
    )
    adapter = LLMAdapter(settings, pricing, guard)

    structured = {
        "ran_at": f"{datetime.now():%Y-%m-%d %H:%M}",
        "agents_per_target": args.agents,
        "max_agents_per_run": settings.max_agents_per_run,
        "pass_required": PASS_REQUIRED,
        "events": [],
    }
    lines = [
        "# ผล Hindcast Batch — exit criteria Phase 0 (ผ่าน ≥ 3/5 เหตุการณ์)",
        f"- วันที่: {datetime.now():%Y-%m-%d %H:%M} | agents/target: {args.agents} "
        f"(cap dev ≤ {settings.max_agents_per_run})",
        "- เกณฑ์ต่อเหตุการณ์ (เข้ม): ทำนายทิศถูก **ครบทุก target** | agent ตอบเสีย = ไม่นับเสียง (fail-closed)",
        "- ⚠️ scenario เลือกตั้ง/การเมือง: ผลเป็น simulation_estimate ระดับ aggregate"
        " — not_field_poll (GOV-02)",
        "",
    ]
    passed = 0
    for _event_dir, event, truth in events:
        print(f"\n== {event.event_id} ==")
        predictions = predict_event(
            adapter,
            event,
            truth,
            agents_per_target=args.agents,
            seed=settings.default_seed,
            on_progress=lambda p: print(
                f"  {p.target_id:<28} โหวต {p.vote_split:<18} → "
                f"{'?' if p.predicted is None else p.predicted} "
                f"(จริง {p.truth}) {'✓' if p.correct else '✗'}"
            ),
        )
        ok = event_passes(predictions)
        passed += ok
        structured["events"].append(
            {
                "event_id": event.event_id,
                "passed": ok,
                "targets": [
                    {
                        "id": p.target_id,
                        "predicted": p.predicted,
                        "truth": p.truth,
                        "correct": p.correct,
                        "votes": p.vote_split,
                    }
                    for p in predictions
                ],
            }
        )
        lines += [f"## {event.event_id} — {'ผ่าน ✅' if ok else 'ไม่ผ่าน ❌'}", ""]
        lines += [
            "| target | เสียงโหวต | ทำนาย | ผลจริง | ถูก? | เหตุผลตัวอย่าง |",
            "|---|---|---|---|---|---|",
        ]
        for p in predictions:
            sample_reason = next((v.reason for v in p.votes if v.answer is not None), "-")
            lines.append(
                f"| {p.target_id} | {p.vote_split} | {p.predicted} | {p.truth} "
                f"| {'✓' if p.correct else '✗'} | {sample_reason[:90]} |"
            )
        lines.append("")

    verdict = "ผ่าน ✅" if passed >= PASS_REQUIRED else "ไม่ผ่าน ❌"
    lines += [
        "## สรุป exit criteria",
        f"- เหตุการณ์ที่ผ่าน: **{passed}/{len(events)}** | เกณฑ์: ≥ {PASS_REQUIRED} → **{verdict}**",
        f"- ต้นทุนจริง: ${guard.spent_usd:.4f}",
    ]
    report = "\n".join(lines)
    # GOV-02: เหตุการณ์ hindcast หลายชุดเป็นเลือกตั้ง/การเมือง — บังคับ election labels
    # ถ้าคำอธิบายเหตุการณ์เข้าข่าย (auto-classify จากชื่อ+claim)
    scenario_text = " ".join(
        e.title + " " + " ".join(t.get("claim", "") for t in e.prediction_targets)
        for _, e, _ in events
    )
    policy = ElectionPolicy(classify_scenario(scenario_text))
    report = policy.apply_labels(report)
    out = ROOT / ".tmp" / f"hindcast-batch-{datetime.now():%Y%m%d-%H%M%S}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    # structured JSON สำหรับ public benchmark page (P1-M2)
    structured.update(passed=passed, total_events=len(events), spent_usd=round(guard.spent_usd, 4))
    latest = ROOT / ".tmp" / "hindcast-batch-latest.json"
    latest.write_text(json.dumps(structured, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nผ่าน {passed}/{len(events)} → {verdict} | ใช้จริง ${guard.spent_usd:.4f}")
    print(f"รายงาน: {out} | JSON: {latest}")


if __name__ == "__main__":
    main()
