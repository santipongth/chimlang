"""M4/M5 — What-if experiment (SIM-04) พร้อม governance ครบวงจร

    uv run python scripts/run_whatif.py --seeds 30 --inject-round 8

ทุก run: audit log → simulation → prediction registry (≥1 record) → export ผ่าน watermark
(ต้องมี PostgreSQL จาก `docker compose up -d` — governance เป็นเงื่อนไขบังคับ ไม่มีทางลัด)
กลไกล้วน ไม่เรียก LLM (ต้นทุน $0) — voice ตัวอย่างจริงดูได้จาก scripts/demo_voice_round.py
"""

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from getpass import getuser
from pathlib import Path

from core.config import get_settings
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
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

    config = {
        "seeds": args.seeds,
        "rounds": args.rounds,
        "inject_round": args.inject_round,
        "agents": n,
        "rumor": RUMOR,
        "event": EVENT,
    }
    config_hash = hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()[:16]
    run_id = f"whatif-{datetime.now():%Y%m%d-%H%M%S}"

    # governance ก่อนเริ่ม (GOV-04): audit ว่าใครสั่งรัน config อะไร
    store = GovernanceStore(settings.postgres_url)
    store.setup()
    store.append_audit(
        actor=getuser(), action="run_started", run_id=run_id, config_hash=config_hash
    )

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

    # prediction registry (TRUST-01): ทุก run ต้องมี record ตรวจสอบได้ ≥ 1
    lo, hi = estimate.ci95
    negative_share = sum(1 for d in estimate.per_seed if d < 0) / len(estimate.per_seed)
    direction = "ลดลง" if estimate.mean_delta < 0 else "ไม่ลดลง"
    store.register_prediction(
        run_id,
        Prediction(
            claim=f"การแถลงชี้แจงทางการต่อข่าวลือลักษณะนี้จะทำให้สัดส่วนผู้เชื่อข่าวลือ{direction}",
            direction=direction,
            confidence=round(min(0.99, negative_share), 2),
            measurement="เทียบ belief rate ใน simulation ซ้ำด้วย population/parameter ชุดใหม่",
            due_date=date.today() + timedelta(days=30),
            model_version="mechanistic-engine@" + config_hash,
        ),
    )
    store.finalize_run(run_id)  # ไม่มี prediction = raise (กฎเหล็กข้อ 3)

    report = render_whatif_report(
        title="คำชี้แจงทางการลดสัดส่วนผู้เชื่อข่าวลือได้แค่ไหน",
        estimate=estimate,
        outcomes=outcomes,
        base_msg_id="rumor",
        event_text=EVENT,
        rounds=args.rounds,
    )
    # export ผ่าน watermark เท่านั้น (GOV-03) — enabled มาจาก env (default true ห้ามปิด prod)
    out = export_report(
        report,
        ROOT / ".tmp" / f"{run_id}.md",
        run_id=run_id,
        enabled=settings.watermark_enabled,
    )
    store.append_audit(
        actor=getuser(),
        action="report_exported",
        run_id=run_id,
        config_hash=config_hash,
        detail=str(out),
    )
    print(report)
    print(f"\nrun_id: {run_id} | delta {estimate.mean_delta:+.1%} CI [{lo:+.1%}, {hi:+.1%}]")
    print(f"governance: audit 2 รายการ + prediction 1 รายการ | รายงาน (มี watermark): {out}")


if __name__ == "__main__":
    main()
