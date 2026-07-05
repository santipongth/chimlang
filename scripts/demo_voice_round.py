"""Demo M3: full loop — กลไกแพร่ + เสียงจริงของ agent (10 ตัวตาม cap, ~$0.002)

รัน simulation 10 rounds ให้ rumor แพร่ แล้วให้ agent ที่ได้ยินเขียน
private_thought vs public_post (เห็น say-do gap/เกรงใจ/ประชดจริงใน trail)

    uv run python scripts/demo_voice_round.py
"""

from datetime import datetime
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from simulation.engine import FabricSimulation, Message
from simulation.persona import PersonaFactory
from simulation.voice import generate_voice

ROOT = Path(__file__).resolve().parents[1]
RUMOR = "ข่าวลือ: เขาว่ากันว่าจะเก็บค่าธรรมเนียมมอเตอร์ไซค์ด้วยคันละ 50 บาทต่อวัน"


def main() -> None:
    settings = get_settings()
    n = settings.max_agents_per_run
    personas = PersonaFactory().sample(n, seed=settings.default_seed, max_agents=n)

    sim = FabricSimulation(personas, seed=settings.default_seed)
    sim.inject(Message("rumor", "rumor", RUMOR, 1, "public_feed"))
    result = sim.run(10)

    heard = [(aid, st) for aid, st in result.states.items() if "rumor" in st.heard]
    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(
        CostEstimator(pricing).estimate([TierLoad(settings.llm_model_crowd, len(heard), 700, 250)])
    )
    adapter = LLMAdapter(settings, pricing, guard)

    lines = [
        f"# Demo เสียง agent (M3) — run {result.run_id} seed {result.seed}",
        f"- วันที่: {datetime.now():%Y-%m-%d %H:%M} | ได้ยินข่าวลือ {len(heard)}/{n} ตัวใน 10 rounds",
        f"- ข้อความ: {RUMOR}",
        "",
    ]
    for aid, st in sorted(heard, key=lambda x: x[1].heard["rumor"]):
        p = st.persona
        voice = generate_voice(
            adapter,
            p,
            RUMOR,
            believed=st.believed.get("rumor", False),
            channel=st.heard_via["rumor"],
            seed=settings.default_seed,
        )
        lines += [
            f"## {aid} — {p.segment_name}",
            f"- ได้ยิน round {st.heard['rumor']} ผ่าน {st.heard_via['rumor']} | "
            f"เชื่อ: {'ใช่' if st.believed.get('rumor') else 'ไม่'} | "
            f"เกรงใจ {p.kreng_jai:.1f} say-do {p.say_do_gap:.1f} ประชด {p.sarcasm_meme:.1f}",
            f"- 🧠 คิดในใจ: {voice.private_thought}",
            f"- 📢 โพสต์จริง: {voice.public_post or '(เลือกไม่โพสต์)'}",
            "",
        ]
    lines.append(f"ใช้เงินจริง: ${guard.spent_usd:.4f}")
    out = ROOT / ".tmp" / f"voice-demo-{datetime.now():%Y%m%d-%H%M%S}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nรายงาน: {out}")


if __name__ == "__main__":
    main()
