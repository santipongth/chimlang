"""M4 — What-if experiment (SIM-04): ข่าวลือ vs ข่าวลือ+คำชี้แจงทางการ

    uv run python scripts/run_whatif.py --seeds 30 --inject-round 8

กลไกล้วน ไม่เรียก LLM (ต้นทุน $0) — voice ตัวอย่างจริงดูได้จาก scripts/demo_voice_round.py
"""

import argparse
from datetime import datetime
from pathlib import Path

from core.config import get_settings
from simulation.engine import Message
from simulation.experiment import run_whatif
from simulation.persona import PersonaFactory
from simulation.report import render_whatif_report

ROOT = Path(__file__).resolve().parents[1]
RUMOR = "ข่าวลือ: จะเก็บค่าธรรมเนียมมอเตอร์ไซค์ด้วยคันละ 50 บาทต่อวัน"
EVENT = "กทม. แถลงชี้แจงทางการ: ร่างมาตรการยกเว้นมอเตอร์ไซค์ทุกประเภท"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--inject-round", type=int, default=8)
    args = parser.parse_args()

    settings = get_settings()
    n = settings.max_agents_dev
    factory = PersonaFactory()

    estimate, outcomes = run_whatif(
        lambda seed: factory.sample(n, seed=seed, max_agents=n),
        seeds=list(range(args.seeds)),
        rounds=args.rounds,
        base_messages=[Message("rumor", "rumor", RUMOR, 1, "public_feed")],
        event=Message(
            "official", "correction", EVENT, args.inject_round, "public_feed", counters="rumor"
        ),
        target_msg_id="rumor",
    )
    report = render_whatif_report(
        title="คำชี้แจงทางการลดสัดส่วนผู้เชื่อข่าวลือได้แค่ไหน",
        estimate=estimate,
        outcomes=outcomes,
        base_msg_id="rumor",
        event_text=EVENT,
        rounds=args.rounds,
    )
    out = ROOT / ".tmp" / f"whatif-{datetime.now():%Y%m%d-%H%M%S}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nรายงาน: {out}")


if __name__ == "__main__":
    main()
