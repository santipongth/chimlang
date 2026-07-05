"""P3-S — วัด scale จริงหลังยกเลิก cap 10 (ผู้ใช้อนุมัติ 6 ก.ค. 2026)

    PYTHONIOENCODING=utf-8 uv run python scripts/measure_scale.py

วัด 3 อย่างแบบซื่อสัตย์:
1. เวลา wall-clock ของ multiverse what-if (5 universes) ที่ 100 และ 1,000 agents (กลไก $0)
2. ต้นทุน voice จริงต่อ call (sample จริง 10 calls × 2 โหมด: thinking on/off)
3. ประมาณการ Standard run เต็มรูป (voice-sparse 15% ของ agent-rounds) เทียบ exit criteria
   Phase 0 (≤ $80) และเป้า PRD (≤ $50) — จากตัวเลขวัดจริง ไม่ใช่สมมติฐานล้วน
"""

import time
from datetime import date, datetime, timedelta
from getpass import getuser
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
from simulation.engine import Message
from simulation.persona import PersonaFactory
from simulation.voice import generate_voice
from trust.universe import run_multiverse_whatif

ROOT = Path(__file__).resolve().parents[1]
RUMOR = "ข่าวลือ: จะเก็บค่าธรรมเนียมมอเตอร์ไซค์ด้วยคันละ 50 บาทต่อวัน"
EVENT = "กทม. แถลงชี้แจงทางการ: ร่างมาตรการยกเว้นมอเตอร์ไซค์ทุกประเภท"
VOICE_SAMPLE = 10
STANDARD_VOICE_CALLS = int(1000 * 30 * 0.15) * 5  # voice-sparse 15% × 5 universes


def measure_mech(n_agents: int, rounds: int) -> tuple[float, int, float]:
    """คืน (วินาที, fragility, delta เฉลี่ยฐาน) ของ multiverse เต็มรูปที่ scale นี้"""
    settings = get_settings()
    t0 = time.perf_counter()
    fragility, _ = run_multiverse_whatif(
        PersonaFactory(),
        n_agents=n_agents,
        max_agents=settings.max_agents_per_run,
        universes=5,
        seeds_per_universe=4,
        rounds=rounds,
        base_messages=[Message("rumor", "rumor", RUMOR, 1, "public_feed")],
        event=Message("official", "correction", EVENT, 8, "public_feed", counters="rumor"),
        target_msg_id="rumor",
        base_seed=settings.default_seed,
    )
    return (
        time.perf_counter() - t0,
        fragility.fragility_index,
        fragility.universes[0].estimate.mean_delta,
    )


def main() -> None:
    settings = get_settings()
    run_id = f"scale-{datetime.now():%Y%m%d-%H%M%S}"
    store = GovernanceStore(settings.postgres_url)
    store.setup()
    store.append_audit(actor=getuser(), action="run_started", run_id=run_id, config_hash="scale")

    lines = [
        "# Scale Measurement (P3-S) — หลังยกเลิก cap 10 agents",
        "",
        f"- วันที่: {datetime.now():%Y-%m-%d %H:%M} | cap ใหม่: "
        f"{settings.max_agents_per_run} agents/run",
        "",
        "## 1) เวลา multiverse what-if (5 universes × 4 seeds × 2 branches, กลไกล้วน $0)",
        "",
        "| agents | rounds | เวลา (วิ) | fragility | delta ฐาน |",
        "|---|---|---|---|---|",
    ]
    for n, rounds in [(100, 30), (1000, 30)]:
        secs, frag, delta = measure_mech(n, rounds)
        print(f"n={n:>5} rounds={rounds}: {secs:.1f}s | fragility {frag} | delta {delta:+.1%}")
        lines.append(f"| {n} | {rounds} | {secs:.1f} | {frag}/100 | {delta:+.1%} |")

    # 2) ต้นทุน voice ต่อ call — วัดจริง
    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(
        CostEstimator(pricing).estimate(
            [TierLoad(settings.llm_model_crowd, VOICE_SAMPLE * 2, 800, 300)]
        )
    )
    adapter = LLMAdapter(settings, pricing, guard)
    personas = PersonaFactory().sample(VOICE_SAMPLE, seed=1, max_agents=settings.max_agents_per_run)
    costs: dict[str, float] = {}
    for label, reasoning in [("thinking-on", None), ("thinking-off", False)]:
        spent0 = guard.spent_usd
        for i, p in enumerate(personas):
            generate_voice(
                adapter,
                p,
                RUMOR,
                believed=True,
                channel="public_feed",
                seed=100 + i,
                reasoning=reasoning,
            )
        costs[label] = (guard.spent_usd - spent0) / VOICE_SAMPLE
        print(f"voice {label}: ${costs[label]:.6f}/call (วัดจาก {VOICE_SAMPLE} calls จริง)")

    lines += [
        "",
        f"## 2) ต้นทุน voice ต่อ call (วัดจริง {VOICE_SAMPLE} calls/โหมด)",
        "",
        f"- thinking on (คุณภาพเต็ม ADR-0001): ${costs['thinking-on']:.6f}/call",
        f"- thinking off (โหมดเร็ว interactive): ${costs['thinking-off']:.6f}/call",
        "",
        "## 3) ประมาณการ Standard run เต็มรูป (1,000×30×5u, voice-sparse 15%)",
        "",
        f"- voice calls ที่ต้องใช้: {STANDARD_VOICE_CALLS:,}",
    ]
    for label in costs:
        total = STANDARD_VOICE_CALLS * costs[label]
        verdict80 = "ผ่าน ✅" if total <= 80 else "ไม่ผ่าน ❌"
        verdict50 = "ผ่าน ✅" if total <= 50 else "ไม่ผ่าน ❌"
        lines.append(
            f"- แบบ {label}: **${total:.2f}** → exit criteria Phase 0 (≤$80): {verdict80} "
            f"| เป้า PRD (≤$50): {verdict50}"
        )
        print(f"standard ({label}): ${total:.2f}")
    lines += [
        "",
        "หมายเหตุซื่อสัตย์: ตัวเลขจาก extrapolation ของต้นทุน/call ที่วัดจริง — การรัน voice "
        f"{STANDARD_VOICE_CALLS:,} calls จริงยังไม่ได้ทำ (จะกิน RUN_BUDGET_USD_CAP); "
        "เวลากลไกวัดเต็มจริงแล้วในตาราง 1",
    ]

    store.register_prediction(
        run_id,
        Prediction(
            claim="Standard run เต็มรูปแบบ voice-sparse จะมีต้นทุนจริงไม่เกิน $80 เมื่อรันครบทั้ง run",
            direction="ไม่เกิน",
            confidence=0.9,
            measurement="รัน standard เต็มรูปครั้งแรกแล้วอ่าน BudgetGuard.spent_usd",
            due_date=date.today() + timedelta(days=30),
            model_version="scale-measurement@extrapolated",
            domain="ทั่วไป",
        ),
    )
    store.finalize_run(run_id)
    out = export_report(
        "\n".join(lines),
        ROOT / "docs" / "reports" / "scale-measurement.md",
        run_id=run_id,
        enabled=settings.watermark_enabled,
    )
    store.append_audit(
        actor=getuser(),
        action="report_exported",
        run_id=run_id,
        config_hash="scale",
        detail=str(out),
    )
    print(f"\nใช้จริง ${guard.spent_usd:.4f} | รายงาน: {out}")


if __name__ == "__main__":
    main()
