"""M4/M5 — What-if experiment (SIM-04) พร้อม governance ครบวงจร + รับเหตุการณ์จริง

    # demo scenario เดิม:
    uv run python scripts/run_whatif.py --seeds 30 --inject-round 8

    # เหตุการณ์/นโยบายจริง (จุดปลดล็อก calibration แท้จริง — เพิ่ม 12 ก.ค. 2026):
    uv run python scripts/run_whatif.py --subject "นโยบาย X ที่จะประกาศ" \
        --rumor "ประเด็น/ความเชื่อที่กำลังแพร่ในสังคม" \
        --event "คำแถลง/มาตรการที่จะปล่อยจริง" \
        --claim "สิ่งที่ทำนายว่าจะเกิด (วัดผลได้จริง)" \
        --measurement "จะวัดด้วยอะไร เช่น โพลจริง/ยอดขาย/มติที่ประชุม" \
        --due-days 14 --domain นโยบาย

ทุก run: PII gate (GOV-01) → election classify (GOV-02) → audit log → simulation →
prediction registry (≥1 record, append-only) → export ผ่าน watermark
เมื่อครบกำหนด: resolve ผ่านหน้า Calibration ใน /app หรือ scripts/resolve_predictions.py
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
from governance.election import ElectionPolicy, classify_scenario
from governance.pii import PIIDetector, load_allowlist
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
from simulation.engine import Message
from simulation.persona import PersonaFactory
from simulation.provenance import build_cards
from simulation.report import render_whatif_report
from trust.universe import run_multiverse_whatif

ROOT = Path(__file__).resolve().parents[1]
RUMOR = "ข่าวลือ: จะเก็บค่าธรรมเนียมมอเตอร์ไซค์ด้วยคันละ 50 บาทต่อวัน"
EVENT = "กทม. แถลงชี้แจงทางการ: ร่างมาตรการยกเว้นมอเตอร์ไซค์ทุกประเภท"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--inject-round", type=int, default=8)
    # --- เหตุการณ์จริง (ไม่ใส่ = demo scenario เดิม) ---
    parser.add_argument("--subject", default="คำชี้แจงทางการลดสัดส่วนผู้เชื่อข่าวลือได้แค่ไหน")
    parser.add_argument("--rumor", default=RUMOR, help="ประเด็น/ความเชื่อที่กำลังแพร่")
    parser.add_argument("--event", default=EVENT, help="คำแถลง/มาตรการที่จะ inject")
    parser.add_argument("--claim", default=None, help="คำทำนายที่วัดผลได้จริง (default: อิงทิศ delta)")
    parser.add_argument("--measurement", default=None, help="วิธีวัดผลจริงเมื่อครบกำหนด")
    parser.add_argument("--due-days", type=int, default=30, help="กี่วันจึงครบกำหนดวัดผล")
    parser.add_argument("--domain", default="ทั่วไป", help="นโยบาย | ธุรกิจ/การตลาด | กระแสสังคม | ทั่วไป")
    parser.add_argument("--agents", type=int, default=None, help="จำนวน agents (default = cap)")
    args = parser.parse_args()

    settings = get_settings()
    n = min(args.agents or settings.max_agents_per_run, settings.max_agents_per_run)
    factory = PersonaFactory()

    # GOV-01: ข้อความจากผู้ใช้ทุกช่องผ่าน PII detector — พบ = ไม่รัน (fail-closed เหมือน ingest)
    if not settings.pii_detector_enabled:
        raise SystemExit("PII detector ถูกปิดอยู่ — ปฏิเสธการรัน (GOV-01 fail-closed)")
    user_text = "\n".join(
        x for x in (args.subject, args.rumor, args.event, args.claim, args.measurement) if x
    )
    pii = PIIDetector(load_allowlist()).check(user_text)
    if pii.blocked:
        raise SystemExit(
            "พบข้อมูลส่วนบุคคลใน input — block ตาม GOV-01: " + "; ".join(pii.block_reasons)
        )

    # GOV-02: จัดประเภท election จาก subject+rumor — เข้าโหมด = รายงานติดป้ายบังคับ 3 ชนิด
    election = ElectionPolicy(classify_scenario(f"{args.subject} {args.rumor}"))
    if election.active:
        print(
            "⚠️ election mode: output ระดับ aggregate เท่านั้น + ป้าย "
            "simulation_estimate/not_field_poll/aggregate_only"
        )

    config = {
        "seeds": args.seeds,
        "rounds": args.rounds,
        "inject_round": args.inject_round,
        "agents": n,
        "subject": args.subject,
        "rumor": args.rumor,
        "event": args.event,
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

    # TRUST-04: ทุก what-if รัน ≥ 5 universes เสมอ (fragility coverage 100%)
    fragility, outcomes = run_multiverse_whatif(
        factory,
        n_agents=n,
        max_agents=n,
        universes=5,
        seeds_per_universe=args.seeds // 5 or 5,
        rounds=args.rounds,
        base_messages=[Message("rumor", "rumor", args.rumor, 1, "public_feed")],
        event=Message(
            "official", "correction", args.event, args.inject_round, "public_feed", counters="rumor"
        ),
        target_msg_id="rumor",
        base_seed=settings.default_seed,
        on_progress=lambda u: print(
            f"  universe {u.universe_id}: delta {u.estimate.mean_delta:+.1%} → {u.conclusion}"
        ),
    )
    estimate = fragility.universes[0].estimate  # สมมติฐานฐาน

    # prediction registry (TRUST-01): ทุก run ต้องมี record ตรวจสอบได้ ≥ 1
    lo, hi = estimate.ci95
    negative_share = sum(1 for d in estimate.per_seed if d < 0) / len(estimate.per_seed)
    direction = fragility.majority_conclusion
    # TRUST-05: confidence ถูก downgrade ตาม fragility (พลิกง่าย = มั่นใจน้อยลง)
    confidence = round(min(0.99, negative_share) * (1 - fragility.fragility_index / 100), 2)
    store.register_prediction(
        run_id,
        Prediction(
            claim=args.claim
            or f"{args.subject}: การชี้แจง/มาตรการนี้จะทำให้สัดส่วนผู้เชื่อประเด็นดังกล่าว{direction}",
            direction=direction,
            confidence=confidence,
            measurement=args.measurement or "ผู้ใช้ป้อนผลจริงเมื่อครบกำหนด (หน้า Calibration ใน /app)",
            due_date=date.today() + timedelta(days=args.due_days),
            model_version="mechanistic-engine@" + config_hash,
            domain=args.domain,
        ),
    )
    store.finalize_run(run_id)  # ไม่มี prediction = raise (กฎเหล็กข้อ 3)

    report = render_whatif_report(
        title=args.subject,
        estimate=estimate,
        outcomes=outcomes,
        base_msg_id="rumor",
        event_text=args.event,
        rounds=args.rounds,
        fragility=fragility,
        provenance_cards=build_cards(),  # TRUST-06: ทุกรายงานมีบัตรที่มา persona
    )
    if election.active:
        report = election.apply_labels(report)  # GOV-02: ป้ายบังคับบน output เลือกตั้ง
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
    print(
        f"\nrun_id: {run_id} | delta {estimate.mean_delta:+.1%} CI [{lo:+.1%}, {hi:+.1%}] "
        f"| fragility {fragility.fragility_index}/100"
    )
    print(f"governance: audit 2 รายการ + prediction 1 รายการ | รายงาน (มี watermark): {out}")


if __name__ == "__main__":
    main()
