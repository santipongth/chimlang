"""Calibration Engine — คิว resolve คำทำนายที่ครบกำหนด (TRUST-02)

    uv run python scripts/resolve_predictions.py                        # ดูคิวที่ครบกำหนด
    uv run python scripts/resolve_predictions.py --id 3 --outcome true --note "อ้างอิงผลจริง..."

การ resolve เป็น append-only: บันทึกแล้วแก้ไม่ได้ (เหมือน registry) — Brier คำนวณอัตโนมัติ
"""

import argparse
from datetime import date
from getpass import getuser

from core.config import get_settings
from governance.store import GovernanceStore
from trust.calibration import render_calibration_dashboard


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="prediction id ที่จะ resolve")
    parser.add_argument(
        "--outcome",
        choices=["true", "partial", "false"],
        help="ผลจริงตรงตาม claim ไหม (partial = เกิดขึ้นบางส่วน → 0.5 ใน Brier)",
    )
    parser.add_argument("--note", default="", help="แหล่งอ้างอิงผลจริง")
    args = parser.parse_args()

    store = GovernanceStore(get_settings().postgres_url)
    store.setup()

    if args.id is not None:
        if args.outcome is None:
            raise SystemExit("ต้องระบุ --outcome true/partial/false คู่กับ --id")
        value = {"true": 1.0, "partial": 0.5, "false": 0.0}[args.outcome]
        brier = store.resolve_prediction(args.id, outcome=value, resolver=getuser(), note=args.note)
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
