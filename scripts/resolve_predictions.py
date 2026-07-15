"""Calibration Engine — คิว resolve คำทำนายที่ครบกำหนด (TRUST-02)

    uv run python scripts/resolve_predictions.py                        # ดูคิวที่ครบกำหนด
    uv run python scripts/resolve_predictions.py --id 3 --outcome true \
      --evidence-url https://example.org/result --evidence-name "ประกาศผล"

การ resolve เป็น append-only: บันทึกแล้วแก้ไม่ได้ (เหมือน registry) — Brier คำนวณอัตโนมัติ
"""

import argparse
from datetime import UTC, date, datetime
from getpass import getuser

from core.config import get_settings
from governance.store import GovernanceStore
from trust.calibration import render_calibration_dashboard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="prediction id ที่จะ resolve")
    parser.add_argument(
        "--outcome",
        choices=["true", "false"],
        help="ผลจริงตรงตาม binary claim หรือไม่",
    )
    parser.add_argument("--evidence-url", default="", help="URL หลักฐานผลจริง")
    parser.add_argument("--evidence-name", default="", help="ชื่อหลักฐานผลจริง")
    parser.add_argument("--observed-at", default="", help="เวลา ISO-8601; ว่าง = ตอนนี้")
    parser.add_argument("--note", default="", help="หมายเหตุเพิ่มเติม")
    args = parser.parse_args()

    store = GovernanceStore(get_settings().postgres_url)
    store.setup()

    if args.id is not None:
        if args.outcome is None:
            raise SystemExit("ต้องระบุ --outcome true/false คู่กับ --id")
        if not args.evidence_url or not args.evidence_name:
            raise SystemExit("ต้องระบุ --evidence-url และ --evidence-name")
        observed_at = (
            datetime.fromisoformat(args.observed_at) if args.observed_at else datetime.now(UTC)
        )
        brier = store.resolve_prediction(
            args.id,
            outcome=args.outcome == "true",
            resolver=getuser(),
            observed_at=observed_at,
            evidence_url=args.evidence_url,
            evidence_name=args.evidence_name,
            note=args.note,
        )
        store.append_audit(
            actor=getuser(),
            action="prediction_resolved",
            run_id=f"prediction-{args.id}",
            config_hash="-",
            detail=f"outcome={args.outcome} brier={brier:.3f}",
        )
        print(f"resolve แล้ว: prediction {args.id} | outcome={args.outcome} | Brier={brier:.3f}")

    due = store.due_unresolved(date.today())
    print(f"\nคิวครบกำหนดที่ยังไม่ resolve: {len(due)} รายการ")
    for p in due:
        print(
            f"  [{p.prediction_id}] due {p.due_date} | {p.domain} "
            f"| conf {p.confidence:.2f} | {p.claim[:70]}"
        )
    print()
    print(render_calibration_dashboard(store.calibration_summary(), as_of=date.today()))


if __name__ == "__main__":
    main()
