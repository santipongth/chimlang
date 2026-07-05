"""P2-M5 — Living Memory (SIM-05) + ถามโลกจำลอง (SIM-08) demo ครบวงจร

    PYTHONIOENCODING=utf-8 uv run python scripts/run_living_world.py [--reset] [--ask "คำถาม"]

วงจร: recall ความจำโลก → รัน simulation ต่อจากสถานะเดิม (preseed จาก belief ล่าสุด)
→ บันทึกผลกลับเข้า memory → (ตัวเลือก) ถามคำถามโดยคำตอบอ้าง trail จริง
"""

import argparse
from datetime import date, datetime, timedelta
from getpass import getuser
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from governance.pii import PIIDetector, load_allowlist
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
from simulation.ask import ask_world, render_answer
from simulation.engine import FabricSimulation, Message
from simulation.memory import WorldMemory, render_memory_context
from simulation.persona import PersonaFactory
from simulation.warroom import _preseed_believers

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "congestion-fee-bkk"
RUMOR = "ข่าวลือ: ค่าธรรมเนียมรถติดจะขยายไปเก็บถนนรองทั่วกรุงเทพฯ ภายในปีเดียว"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="ล้างโลก (reset world)")
    parser.add_argument("--ask", help="คำถามต่อโลกจำลอง (SIM-08)")
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()

    settings = get_settings()
    run_id = f"living-{datetime.now():%Y%m%d-%H%M%S}"
    store = GovernanceStore(settings.postgres_url)
    store.setup()
    memory = WorldMemory(settings.postgres_url, PIIDetector(load_allowlist()))
    memory.setup()

    if args.reset:
        removed = memory.reset_world(WORKSPACE)
        store.append_audit(
            actor=getuser(),
            action="world_reset",
            run_id=run_id,
            config_hash="-",
            detail=f"workspace={WORKSPACE} removed={removed}",
        )
        print(f"ล้างโลก {WORKSPACE} แล้ว ({removed} ความจำ)")
        return

    store.append_audit(actor=getuser(), action="run_started", run_id=run_id, config_hash=WORKSPACE)

    recalled = memory.recall(WORKSPACE, limit=5)
    prior_belief = memory.latest_belief(WORKSPACE)
    print("ความจำของโลกนี้:")
    print(render_memory_context(recalled))
    print(
        f"\nสถานะความเชื่อที่โลกจำได้: {prior_belief:.0%}"
        if prior_belief is not None
        else "\n(run แรกของโลกนี้)"
    )

    personas = PersonaFactory().sample(
        settings.max_agents_dev, seed=settings.default_seed, max_agents=settings.max_agents_dev
    )
    sim = FabricSimulation(personas, seed=settings.default_seed + len(recalled))
    if prior_belief is not None:
        # โลกจำได้ — เริ่มจากสถานะเดิม ไม่ใช่ศูนย์ (หัวใจ SIM-05)
        sim.preseed(
            Message("rumor", "rumor", RUMOR, 0, "public_feed"),
            _preseed_believers(personas, prior_belief),
        )
    else:
        sim.inject(Message("rumor", "rumor", RUMOR, 1, "public_feed"))
    result = sim.run(args.rounds)
    belief = sum(1 for st in result.states.values() if st.believed.get("rumor")) / len(
        result.states
    )
    print(f"หลัง run นี้: ผู้เชื่อข่าวลือ {belief:.0%}")

    memory.remember(
        WORKSPACE,
        "sim_result",
        f"run {run_id}: สัดส่วนผู้เชื่อข่าวลือขยายพื้นที่เก็บเงิน = {belief:.0%}",
        belief_share=belief,
        source_run_id=run_id,
    )

    store.register_prediction(
        run_id,
        Prediction(
            claim=f"ถ้าไม่มีการชี้แจง สัดส่วนผู้เชื่อข่าวลือนี้จะไม่ต่ำกว่า {belief:.0%} ใน run ถัดไปของโลกนี้",
            direction="ไม่ลดลง",
            confidence=0.6,
            measurement="เทียบ belief share ของ run ถัดไปใน workspace เดียวกัน",
            due_date=date.today() + timedelta(days=14),
            model_version="living-world@mechanistic",
            domain="กระแสสังคม",
        ),
    )
    store.finalize_run(run_id)

    report_lines = [
        f"# Living World Report (SIM-05): {WORKSPACE}",
        "",
        "> ⚠️ simulation_estimate — โลกจำลองต่อเนื่องข้าม run (cap ≤ 10 agents)",
        "",
        f"- ความจำก่อน run: {len(recalled)} รายการ | belief ตั้งต้น: "
        + (f"{prior_belief:.0%}" if prior_belief is not None else "เริ่มใหม่"),
        f"- belief หลัง run: {belief:.0%}",
        "",
        "## ความจำของโลก (ล่าสุดก่อน)",
        "",
        render_memory_context(memory.recall(WORKSPACE, limit=10)),
    ]

    if args.ask:
        pricing = PricingRegistry.from_yaml()
        guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
        guard.check_estimate(
            CostEstimator(pricing).estimate([TierLoad(settings.llm_model_analyst, 1, 3000, 500)])
        )
        adapter = LLMAdapter(settings, pricing, guard)
        ta = ask_world(adapter, result, args.ask, msg_id="rumor", seed=settings.default_seed)
        answer_md = render_answer(ta)
        print("\n" + answer_md)
        report_lines += ["", "## ถาม-ตอบจาก trail (SIM-08)", "", answer_md]

    out = export_report(
        "\n".join(report_lines),
        ROOT / ".tmp" / f"{run_id}.md",
        run_id=run_id,
        enabled=settings.watermark_enabled,
    )
    store.append_audit(
        actor=getuser(),
        action="report_exported",
        run_id=run_id,
        config_hash=WORKSPACE,
        detail=str(out),
    )
    print(f"\nrun_id: {run_id} | รายงาน (มี watermark): {out}")


if __name__ == "__main__":
    main()
