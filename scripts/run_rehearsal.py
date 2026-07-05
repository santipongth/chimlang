"""P2-M1 — ซ้อมแถลงข่าวสด (REH-01) กับนักข่าว/ชาวเน็ตจำลอง

    โหมดสด (พิมพ์ตอบเอง, พิมพ์ /จบ เพื่อรับ scorecard):
        PYTHONIOENCODING=utf-8 uv run python scripts/run_rehearsal.py

    โหมด scripted (สำหรับ demo/test — อ่านคำตอบจากไฟล์ทีละบรรทัด):
        PYTHONIOENCODING=utf-8 uv run python scripts/run_rehearsal.py --answers answers.txt

ครบวงจร governance: audit → ซ้อม → scorecard → prediction → watermark export
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
from simulation.persona import PersonaFactory
from simulation.rehearsal import JOURNALISTS, RehearsalSession, render_rehearsal_report

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DOCS = [
    "data/samples/corpus/2026-05-26-ร่างขอบเขตพื้นที่เก็บค่าธรรมเนียม.md",
    "data/samples/corpus/2026-05-12-มาตรการลดค่าโดยสารช่วงเปลี่ยนผ่าน.md",
]
N_NETIZENS = 4  # + นักข่าว 3 = ผู้เข้าร่วม 7 ≤ cap 10
MAX_TURNS = 8


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", help="ไฟล์คำตอบ (โหมด scripted) — บรรทัดละคำตอบ")
    parser.add_argument("--turns", type=int, default=MAX_TURNS, help="จำนวนคำถามสูงสุด")
    args = parser.parse_args()

    settings = get_settings()
    scenario = "\n\n".join((ROOT / p).read_text(encoding="utf-8") for p in SCENARIO_DOCS)
    scenario_hash = hashlib.sha256(scenario.encode()).hexdigest()[:16]
    run_id = f"rehearsal-{datetime.now():%Y%m%d-%H%M%S}"

    scripted = None
    if args.answers:
        scripted = [
            ln.strip()
            for ln in Path(args.answers).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        args.turns = min(args.turns, len(scripted))

    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(
        CostEstimator(pricing).estimate(
            [
                TierLoad(settings.llm_model_crowd, args.turns * 3, 3500, 250),  # ถาม + react 2
                TierLoad(settings.llm_model_analyst, 2, 4000, 800),  # scorecard + retry
            ]
        )
    )

    store = GovernanceStore(settings.postgres_url)
    store.setup()
    store.append_audit(
        actor=getuser(), action="run_started", run_id=run_id, config_hash=scenario_hash
    )

    adapter = LLMAdapter(settings, pricing, guard)
    netizens = PersonaFactory().sample(
        N_NETIZENS, seed=settings.default_seed, max_agents=settings.max_agents_per_run
    )
    session = RehearsalSession(
        adapter,
        scenario,
        netizens,
        seed=settings.default_seed,
        max_agents=settings.max_agents_per_run,
    )

    print(
        f"=== ซ้อมแถลงข่าว: มาตรการค่าธรรมเนียมรถติด "
        f"({len(JOURNALISTS)} นักข่าว + {N_NETIZENS} ชาวเน็ต) ==="
    )
    print("พิมพ์คำตอบแล้ว Enter | พิมพ์ /จบ เพื่อปิดงานแถลงและรับ scorecard\n")

    for i in range(args.turns):
        role, question, latency = session.next_question()
        print(f"\n📣 [{role.name}] ({latency:.1f} วิ): {question}")
        if scripted is not None:
            answer = scripted[i]
            print(f"🎤 ตอบ (scripted): {answer}")
        else:
            answer = input("🎤 ตอบ: ").strip()
        if answer in ("/จบ", "/end", ""):
            break
        turn = session.submit_answer(role, question, answer, latency)
        for r in turn.reactions:
            print(f"   💬 {r}")

    if not session.turns:
        raise SystemExit("ไม่มีการถาม-ตอบเลย — ไม่มีอะไรให้ประเมิน")

    print("\n⏳ analyst กำลังประเมิน scorecard...")
    card = session.scorecard()

    top_inflamed = card.inflamed[0] if card.inflamed else "(ไม่พบประเด็นราดน้ำมัน)"
    store.register_prediction(
        run_id,
        Prediction(
            claim=(
                f"หากแถลงจริงด้วยคำตอบชุดนี้ ประเด็น '{top_inflamed[:80]}' "
                "จะถูกสื่อ/โซเชียลหยิบไปวิจารณ์เป็นประเด็นลบหลัก"
            ),
            direction="เกิดขึ้น",
            confidence=0.6 if card.inflamed else 0.2,
            measurement="ตรวจข่าว/โซเชียลหลังการแถลงจริง (ถ้ามี) ว่าประเด็นนี้ถูกหยิบยกหรือไม่",
            due_date=date.today() + timedelta(days=30),
            model_version=f"rehearsal@{scenario_hash}",
            domain="นโยบาย",
        ),
    )
    store.finalize_run(run_id)

    report = render_rehearsal_report("มาตรการค่าธรรมเนียมรถติด กทม.", session.turns, card)
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
    print(f"\nrun_id: {run_id} | ใช้จริง ${guard.spent_usd:.4f}")
    print(f"Scorecard (มี watermark): {out}")


if __name__ == "__main__":
    main()
