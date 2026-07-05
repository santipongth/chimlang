"""P1-M4 — Red Team Swarm โจมตีร่างนโยบายค่าธรรมเนียมรถติด (scenario จาก corpus)

    uv run python scripts/run_redteam.py

ครบวงจร governance: audit → โจมตี+ให้คะแนน → prediction registry → watermark export
"""

import hashlib
from datetime import date, datetime, timedelta
from getpass import getuser
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
from simulation.redteam import ROLES, render_attack_surface_report, run_red_team

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DOCS = [
    "data/samples/corpus/2026-05-26-ร่างขอบเขตพื้นที่เก็บค่าธรรมเนียม.md",
    "data/samples/corpus/2026-05-12-มาตรการลดค่าโดยสารช่วงเปลี่ยนผ่าน.md",
]
ATTACKS_PER_ROLE = 2


def main() -> None:
    settings = get_settings()
    scenario = "\n\n".join((ROOT / p).read_text(encoding="utf-8") for p in SCENARIO_DOCS)
    scenario_hash = hashlib.sha256(scenario.encode()).hexdigest()[:16]
    run_id = f"redteam-{datetime.now():%Y%m%d-%H%M%S}"

    n_calls = len(ROLES) * ATTACKS_PER_ROLE
    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(
        CostEstimator(pricing).estimate(
            [
                TierLoad(settings.llm_model_crowd, n_calls, 6000, 350),
                TierLoad(settings.llm_model_analyst, n_calls, 2500, 250),
            ]
        )
    )

    store = GovernanceStore(settings.postgres_url)
    store.setup()
    store.append_audit(
        actor=getuser(), action="run_started", run_id=run_id, config_hash=scenario_hash
    )

    adapter = LLMAdapter(settings, pricing, guard)
    scored = run_red_team(
        adapter,
        scenario,
        attacks_per_role=ATTACKS_PER_ROLE,
        seed=settings.default_seed,
        on_progress=lambda s: print(
            f"  [{s.attack.role_name:<24}] risk {s.risk:>2} ({s.likelihood}x{s.damage}) "
            f"{s.attack.attack[:60]}"
        ),
    )
    if not scored:
        raise SystemExit("red team ไม่ได้ประเด็นโจมตีเลย — ตรวจ model/prompt")

    top = scored[0]
    store.register_prediction(
        run_id,
        Prediction(
            claim=(
                "ประเด็นเสี่ยงอันดับ 1 ที่ red team ระบุ "
                f"({top.attack.role_name}: {top.attack.exploit[:80]}) "
                "จะปรากฏเป็นข้อวิจารณ์จริงในเวทีประชาพิจารณ์/สื่อภายในกำหนด"
            ),
            direction="เกิดขึ้น",
            confidence=round(min(0.95, top.likelihood / 5), 2),
            measurement="ตรวจข่าว/บันทึกประชาพิจารณ์จริงว่าประเด็นนี้ถูกหยิบยกหรือไม่",
            due_date=date.today() + timedelta(days=45),
            model_version=f"redteam@{scenario_hash}",
            domain="นโยบาย",
        ),
    )
    store.finalize_run(run_id)

    report = render_attack_surface_report("ร่างมาตรการค่าธรรมเนียมรถติด กทม.", scored)
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
    print(
        f"\nประเด็นโจมตี {len(scored)} รายการ | top risk = {top.risk} | ใช้จริง ${guard.spent_usd:.4f}"
    )
    print(f"Attack Surface Report (มี watermark): {out}")


if __name__ == "__main__":
    main()
