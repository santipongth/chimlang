"""P2-M2 — Game Mode (REH-03): เกมหลายตากับฝ่ายค้าน/ผู้เสียประโยชน์จำลอง

    โหมดสด:      PYTHONIOENCODING=utf-8 uv run python scripts/run_game.py
    โหมด scripted: PYTHONIOENCODING=utf-8 uv run python scripts/run_game.py --moves moves.txt

ครบวงจร governance: audit → เกม ≥3 ตา → decision tree → prediction → watermark export
"""

import argparse
import hashlib
from datetime import date, datetime, timedelta
from getpass import getuser
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
from simulation.game import MIN_TURNS, GameSession, render_game_report
from simulation.persona import PersonaFactory

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DOCS = [
    "data/samples/corpus/2026-05-26-ร่างขอบเขตพื้นที่เก็บค่าธรรมเนียม.md",
    "data/samples/corpus/2026-05-12-มาตรการลดค่าโดยสารช่วงเปลี่ยนผ่าน.md",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moves", help="ไฟล์การเดินของเรา (โหมด scripted) — บรรทัดละ 1 ตา")
    parser.add_argument("--turns", type=int, default=MIN_TURNS)
    args = parser.parse_args()

    settings = get_settings()
    scenario = "\n\n".join((ROOT / p).read_text(encoding="utf-8") for p in SCENARIO_DOCS)
    scenario_hash = hashlib.sha256(scenario.encode()).hexdigest()[:16]
    run_id = f"game-{datetime.now():%Y%m%d-%H%M%S}"

    scripted = None
    if args.moves:
        scripted = [
            ln.strip()
            for ln in Path(args.moves).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        args.turns = min(args.turns, len(scripted)) if scripted else args.turns

    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(
        CostEstimator(pricing).estimate(
            [
                TierLoad(settings.llm_model_analyst, args.turns + 1, 3000, 700),
                TierLoad(settings.llm_model_crowd, args.turns * 2, 800, 250),
            ]
        )
    )

    store = GovernanceStore(settings.postgres_url)
    store.setup()
    store.append_audit(
        actor=getuser(), action="run_started", run_id=run_id, config_hash=scenario_hash
    )

    adapter = LLMAdapter(settings, pricing, guard)
    personas = PersonaFactory().sample(
        settings.max_agents_per_run,
        seed=settings.default_seed,
        max_agents=settings.max_agents_per_run,
    )
    session = GameSession(adapter, scenario, personas, seed=settings.default_seed)

    print(f"=== Game Mode: มาตรการค่าธรรมเนียมรถติด vs ฝ่ายค้าน ({args.turns} ตา) ===\n")
    for i in range(args.turns):
        if scripted is not None:
            move = scripted[i]
            print(f"🟦 ตา {i + 1} — เราเดิน (scripted): {move}")
        else:
            move = input(f"🟦 ตา {i + 1} — เราเดิน: ").strip()
            if not move:
                break
        turn = session.play_turn(move)
        print(f"🟥 ฝ่ายตรงข้ามตอบ: {turn.opp_move}")
        print(f"   ⚖️ สังคมเชื่อฝั่งเรา {turn.belief_ours:.0%} / ฝั่งตรงข้าม {turn.belief_opp:.0%}")
        for v in turn.voices:
            print(f"   💬 {v}")
        print()

    print("⏳ analyst กำลังสรุป decision tree...")
    tree = session.decision_tree()

    last = session.turns[-1]
    winning = last.belief_ours >= last.belief_opp
    store.register_prediction(
        run_id,
        Prediction(
            claim=(
                "แนวการตอบโต้หลักของฝ่ายค้านต่อแผนนี้ "
                f"('{session.turns[0].opp_move[:70]}') จะปรากฏในการเคลื่อนไหวจริง"
            ),
            direction="เกิดขึ้น",
            confidence=0.55,
            measurement="ตรวจข่าว/แถลงการณ์ฝ่ายคัดค้านจริงภายในกำหนด",
            due_date=date.today() + timedelta(days=45),
            model_version=f"game@{scenario_hash}",
            domain="นโยบาย",
        ),
    )
    store.finalize_run(run_id)

    title = "มาตรการค่าธรรมเนียมรถติด กทม. vs ฝ่ายค้าน"
    report = render_game_report(title, session.turns, tree)
    out = export_report(
        report, ROOT / ".tmp" / f"{run_id}.md", run_id=run_id, enabled=settings.watermark_enabled
    )
    store.append_audit(
        actor=getuser(),
        action="report_exported",
        run_id=run_id,
        config_hash=scenario_hash,
        detail=str(out),
    )
    print(report)
    standing = "นำ" if winning else "ตามหลัง"
    print(f"\nrun_id: {run_id} | ฝั่งเรา{standing}เมื่อจบเกม | ใช้จริง ${guard.spent_usd:.4f}")
    print(f"รายงาน (มี watermark): {out}")


if __name__ == "__main__":
    main()
