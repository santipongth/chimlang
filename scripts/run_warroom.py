"""P2-M3 — Live War Room (REH-04/05): sync → forecast 48 ชม. → divergence alarm

    PYTHONIOENCODING=utf-8 uv run python scripts/run_warroom.py

วงจรกลไกล้วน (ไม่เรียก LLM — cost $0, deterministic): อ่าน feed aggregate →
พยากรณ์ envelope ต่อรอบ → เทียบค่าจริงรอบถัดไป → alarm เมื่อหลุดทุก scenario
"""

import hashlib
from datetime import date, datetime, timedelta
from getpass import getuser
from pathlib import Path

from core.config import get_settings
from core.run_context import RunContext
from governance.pii import PIIDetector, load_allowlist
from governance.store import GovernanceStore, Prediction
from governance.watermark import export_report
from simulation.persona import PersonaFactory
from simulation.warroom import (
    check_divergence,
    forecast_48h,
    load_feed,
    render_warroom_report,
)

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "samples" / "warroom" / "feed-demo.yaml"
NARRATIVE = "ข่าวลือ: ค่าธรรมเนียมรถติดถูกเก็บเข้ากระเป๋าใครไม่รู้ ไม่ถึงขนส่งสาธารณะจริง"


def main() -> None:
    settings = get_settings()
    run_id = f"warroom-{datetime.now():%Y%m%d-%H%M%S}"
    ctx = RunContext(run_id=run_id, seed=settings.default_seed)  # live mode — ไม่ใช่ hindcast
    config_hash = hashlib.sha256(FEED.read_bytes()).hexdigest()[:16]

    store = GovernanceStore(settings.postgres_url)
    store.setup()
    store.append_audit(
        actor=getuser(), action="run_started", run_id=run_id, config_hash=config_hash
    )

    detector = PIIDetector(load_allowlist())
    observations = load_feed(FEED, ctx, detector)  # SIM-11 gate + PII check ในตัว
    personas = PersonaFactory().sample(
        settings.max_agents_dev, seed=settings.default_seed, max_agents=settings.max_agents_dev
    )

    forecasts, divergences = [], []
    for obs in observations:
        if forecasts:
            d = check_divergence(forecasts[-1], obs)
            divergences.append(d)
            flag = "🚨 ALARM" if d.alarm else "ปกติ"
            bounds = f"[{d.bounds[0]:.0%},{d.bounds[1]:.0%}]" if d.bounds else "-"
            print(f"t+{obs.t_hour:>3}: จริง {obs.value:.0%} vs ซอง {bounds} → {flag}")
        fc = forecast_48h(personas, NARRATIVE, obs, base_seed=settings.default_seed)
        forecasts.append(fc)
        lo, hi = fc.envelope[-1]
        print(f"       พยากรณ์ 48 ชม. ข้างหน้า: [{lo:.0%}, {hi:.0%}]")

    latest = forecasts[-1]
    lo, hi = latest.envelope[-1]
    store.register_prediction(
        run_id,
        Prediction(
            claim=(
                f"สัดส่วนผู้เชื่อ narrative นี้ ณ t+{latest.made_at_hour + 48} ชม. "
                f"จะอยู่ในช่วง [{lo:.0%}, {hi:.0%}]"
            ),
            direction="อยู่ในช่วง",
            confidence=0.7,
            measurement="เทียบค่าจริงจาก feed aggregate เมื่อถึงเวลา",
            due_date=date.today() + timedelta(days=2),
            model_version=f"warroom@{config_hash}",
            domain="กระแสสังคม",
        ),
    )
    store.finalize_run(run_id)

    report = render_warroom_report(
        "ดราม่าค่าธรรมเนียมรถติด (feed จำลอง)", NARRATIVE, forecasts, divergences
    )
    out = export_report(
        report, ROOT / ".tmp" / f"{run_id}.md", run_id=run_id, enabled=settings.watermark_enabled
    )
    store.append_audit(
        actor=getuser(),
        action="report_exported",
        run_id=run_id,
        config_hash=config_hash,
        detail=str(out),
    )
    print("\n" + report)
    print(f"\nrun_id: {run_id} | รายงาน (มี watermark): {out}")


if __name__ == "__main__":
    main()
