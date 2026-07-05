"""สร้าง Public Benchmark Page (exit criteria Phase 1 ข้อ 3)

    uv run python scripts/build_benchmark_page.py

อ่าน hindcast JSON ล่าสุด + calibration จาก DB → export ผ่าน watermark ไป docs/reports/
(เผยแพร่ทั้งผ่านและไม่ผ่านเสมอ — ห้าม cherry-pick)
"""

from datetime import date, datetime
from pathlib import Path

from core.config import get_settings
from governance.store import GovernanceStore
from governance.watermark import export_report
from trust.calibration import render_benchmark_page

ROOT = Path(__file__).resolve().parents[1]
HINDCAST_JSON = ROOT / ".tmp" / "hindcast-batch-latest.json"


def main() -> None:
    settings = get_settings()
    if not HINDCAST_JSON.exists():
        raise SystemExit("ยังไม่มีผล hindcast — รัน scripts/run_hindcast_batch.py ก่อน")
    store = GovernanceStore(settings.postgres_url)
    store.setup()

    page = render_benchmark_page(
        hindcast_json_path=HINDCAST_JSON,
        calibration=store.calibration_summary(),
        as_of=date.today(),
    )
    run_id = f"benchmark-page-{datetime.now():%Y%m%d-%H%M%S}"
    out = export_report(
        page,
        ROOT / "docs" / "reports" / "public-benchmark.md",
        run_id=run_id,
        enabled=settings.watermark_enabled,
    )
    print(f"benchmark page (มี watermark): {out}")


if __name__ == "__main__":
    main()
