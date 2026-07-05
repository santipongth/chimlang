"""tests P1-M2: Brier + resolve append-only (DB จริง), due queue, dashboard/page generator"""

import json
from datetime import date, timedelta

import pytest

from governance.store import DomainCalibration, GovernanceStore, Prediction
from trust.calibration import render_benchmark_page, render_calibration_dashboard

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


@pytest.fixture(scope="module")
def store() -> GovernanceStore:
    s = GovernanceStore(DSN)
    try:
        s.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    return s


def _prediction(confidence: float, domain: str = "ทดสอบ-calibration") -> Prediction:
    return Prediction(
        claim="claim ทดสอบ calibration",
        direction="เกิดขึ้น",
        confidence=confidence,
        measurement="เทียบผลจริง",
        due_date=date.today() - timedelta(days=1),  # ครบกำหนดแล้ว
        model_version="test",
        domain=domain,
    )


def _latest_prediction_id(store: GovernanceStore, run_id: str) -> int:
    import psycopg

    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "SELECT id FROM prediction_registry WHERE run_id = %s ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()[0]


def test_due_queue_and_brier_math(store):
    store.register_prediction("run-cal1", _prediction(confidence=0.8))
    pid = _latest_prediction_id(store, "run-cal1")

    due_ids = [p.prediction_id for p in store.due_unresolved(date.today())]
    assert pid in due_ids  # ครบกำหนดและยังไม่ resolve → ต้องอยู่ในคิว

    brier = store.resolve_prediction(pid, outcome=True, resolver="test")
    assert brier == pytest.approx((0.8 - 1.0) ** 2)  # = 0.04

    assert pid not in [p.prediction_id for p in store.due_unresolved(date.today())]


def test_brier_when_wrong(store):
    store.register_prediction("run-cal2", _prediction(confidence=0.9))
    pid = _latest_prediction_id(store, "run-cal2")
    brier = store.resolve_prediction(pid, outcome=False, resolver="test")
    assert brier == pytest.approx(0.81)  # มั่นใจ 0.9 แต่ผิด = โดนลงโทษหนัก


def test_resolution_append_only_and_no_double_resolve(store):
    import psycopg

    store.register_prediction("run-cal3", _prediction(confidence=0.6))
    pid = _latest_prediction_id(store, "run-cal3")
    store.resolve_prediction(pid, outcome=True, resolver="test")

    with pytest.raises(psycopg.errors.UniqueViolation):
        store.resolve_prediction(pid, outcome=False, resolver="test")  # แก้ผลย้อนหลังไม่ได้
    with psycopg.connect(DSN) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute(
                "UPDATE prediction_resolution SET outcome = false WHERE prediction_id = %s", (pid,)
            )
    with psycopg.connect(DSN) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM prediction_resolution WHERE prediction_id = %s", (pid,))


def test_calibration_summary_by_domain(store):
    rows = store.calibration_summary()
    row = next((r for r in rows if r.domain == "ทดสอบ-calibration"), None)
    assert row is not None and row.resolved >= 3
    assert 0.0 <= row.mean_brier <= 1.0


def test_dashboard_renders_empty_and_filled():
    empty = render_calibration_dashboard([], as_of=date(2026, 7, 5))
    assert "ยังไม่มี prediction" in empty
    filled = render_calibration_dashboard(
        [DomainCalibration(domain="นโยบาย", resolved=4, mean_brier=0.12)],
        as_of=date(2026, 7, 5),
    )
    assert "นโยบาย" in filled and "0.120" in filled and "✅" in filled


def test_benchmark_page_shows_failures_too(tmp_path):
    hc = {
        "ran_at": "2026-07-05",
        "agents_per_target": 5,
        "max_agents_dev": 10,
        "pass_required": 3,
        "passed": 4,
        "total_events": 5,
        "spent_usd": 0.08,
        "events": [
            {
                "event_id": "ev-pass",
                "passed": True,
                "targets": [
                    {"id": "t1", "predicted": True, "truth": True, "correct": True, "votes": "5จริง"}
                ],
            },
            {
                "event_id": "ev-fail",
                "passed": False,
                "targets": [
                    {
                        "id": "t2",
                        "predicted": False,
                        "truth": True,
                        "correct": False,
                        "votes": "1จริง/2ไม่จริง",
                    }
                ],
            },
        ],
    }
    p = tmp_path / "hc.json"
    p.write_text(json.dumps(hc, ensure_ascii=False), encoding="utf-8")
    page = render_benchmark_page(hindcast_json_path=p, calibration=[], as_of=date(2026, 7, 5))
    assert "ev-fail" in page and "❌" in page  # ไม่ผ่านต้องโชว์ ห้าม cherry-pick
    assert "not_field_poll" in page
    assert "ข้อจำกัด" in page and "training data" in page
