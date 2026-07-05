"""M1 gate — รัน adversarial leak test กับ hindcast event

    uv run python scripts/run_leak_test.py \
        --event data/samples/hindcast/2565-bkk-governor-election \
        --questions data/benchmark/leak_questions_2565_bkk_election.yaml

ประเมิน cost ก่อนเริ่ม (เคารพ RUN_BUDGET_USD_CAP) แล้วเขียนรายงานลง .tmp/
"""

import argparse
from datetime import datetime
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from trust.hindcast import load_event
from trust.hindcast.leaktest import (
    PASS_THRESHOLD,
    leak_rate,
    load_questions,
    render_report,
    run_leak_test,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, help="โฟลเดอร์ hindcast event")
    parser.add_argument("--questions", required=True, help="ไฟล์ชุดคำถามล่อ (yaml)")
    parser.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนข้อ (สำหรับ dry-run)")
    args = parser.parse_args()

    settings = get_settings()
    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)

    event = load_event(args.event)
    questions = load_questions(args.questions)
    if args.limit:
        questions = questions[: args.limit]

    print(f"event: {event.event_id} | cutoff: {event.cutoff_date} | คำถาม: {len(questions)} ข้อ")
    print(
        f"เอกสาร before ผ่าน filter: {len(event.before_docs)} | ถูก block: {len(event.blocked_paths)}"
    )

    # cost estimate ก่อนเริ่ม (กฎ Cost guard) — ค่า calibrate จาก run จริงรอบ 1
    # (ภาษาไทยกิน token หนัก: system prompt + เอกสาร 3 ชิ้น ≈ 20K token/call)
    n = len(questions)
    estimate = CostEstimator(pricing).estimate(
        [
            TierLoad(
                settings.llm_model_crowd, calls=n, avg_input_tokens=20000, avg_output_tokens=400
            ),
            TierLoad(
                settings.llm_model_analyst, calls=n, avg_input_tokens=1800, avg_output_tokens=300
            ),
        ]
    )
    guard.check_estimate(estimate)
    print(
        f"cost estimate: ${estimate.total_usd:.4f} (cap ${settings.run_budget_usd_cap:.2f}) → เริ่มได้"
    )

    adapter = LLMAdapter(settings, pricing, guard)
    verdicts = run_leak_test(
        adapter,
        event,
        questions,
        seed=settings.default_seed,
        on_progress=lambda v: print(
            f"  {v.question.id:<4} {'LEAK' if v.counted_as_leak else 'ok'}"
        ),
    )

    rate = leak_rate(verdicts)
    report = render_report(event, verdicts, spent_usd=guard.spent_usd)
    out_dir = ROOT / ".tmp"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"leak-report-{event.event_id}-{datetime.now():%Y%m%d-%H%M%S}.md"
    out_path.write_text(report, encoding="utf-8")

    print(
        f"\nleak rate: {rate:.1%} | เกณฑ์: ≤ {PASS_THRESHOLD:.0%} | "
        + ("ผ่าน" if rate <= PASS_THRESHOLD else "ไม่ผ่าน")
    )
    print(f"ใช้เงินจริง: ${guard.spent_usd:.4f}")
    print(f"รายงาน: {out_path}")


if __name__ == "__main__":
    main()
