"""tests M5: watermark (visible+machine, fail-closed), audit/registry append-only ที่ DB จริง"""

from datetime import date

import pytest

from governance.store import GovernanceStore, Prediction, RunWithoutPredictionError
from governance.watermark import (
    WATERMARK_LABEL,
    WatermarkDisabledError,
    apply_watermark,
    export_report,
    verify_watermark,
)

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"

# --- watermark (GOV-03) ---


def test_watermark_has_visible_and_machine_layers():
    out = apply_watermark("# รายงานทดสอบ", run_id="run-xyz")
    assert WATERMARK_LABEL in out  # visible
    assert "run-xyz" in out
    info = verify_watermark(out)  # machine-readable
    assert info is not None
    assert info.run_id == "run-xyz"
    assert info.label == WATERMARK_LABEL


def test_watermark_disabled_refuses_export(tmp_path):
    with pytest.raises(WatermarkDisabledError):
        apply_watermark("x", run_id="r", enabled=False)
    with pytest.raises(WatermarkDisabledError):
        export_report("x", tmp_path / "out.md", run_id="r", enabled=False)


def test_export_report_writes_watermarked_file(tmp_path):
    path = export_report("# เนื้อหา", tmp_path / "report.md", run_id="run-abc")
    text = path.read_text(encoding="utf-8")
    assert verify_watermark(text).run_id == "run-abc"
    assert "# เนื้อหา" in text


def test_plain_text_has_no_watermark():
    assert verify_watermark("รายงานที่ไม่ผ่าน export_report") is None


# --- audit log + prediction registry (GOV-04 / TRUST-01) — DB จริงใน docker ---


@pytest.fixture(scope="module")
def store() -> GovernanceStore:
    s = GovernanceStore(DSN)
    try:
        s.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    return s


def _prediction() -> Prediction:
    return Prediction(
        claim="คำชี้แจงทางการจะลดสัดส่วนผู้เชื่อข่าวลือ",
        direction="ลดลง",
        confidence=0.9,
        measurement="เทียบ belief rate จาก follow-up simulation",
        due_date=date(2026, 8, 5),
        model_version="qwen/qwen3.5-flash-02-23@2026-07-05",
    )


def test_audit_append_and_update_delete_blocked_at_db(store):
    import psycopg

    store.append_audit(actor="test", action="run_started", run_id="run-t1", config_hash="deadbeef")
    with psycopg.connect(DSN) as conn:
        row_id = conn.execute(
            "SELECT id FROM audit_log WHERE run_id = 'run-t1' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        # UPDATE ต้องถูก DB ปฏิเสธเอง (ไม่ใช่แค่ convention ฝั่งโค้ด)
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE audit_log SET actor = 'hacker' WHERE id = %s", (row_id,))
    with psycopg.connect(DSN) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM audit_log WHERE id = %s", (row_id,))


def test_prediction_registry_append_only_at_db(store):
    import psycopg

    store.register_prediction("run-t2", _prediction())
    assert store.predictions_for_run("run-t2") >= 1
    with psycopg.connect(DSN) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE prediction_registry SET confidence = 0 WHERE run_id = 'run-t2'")
    with psycopg.connect(DSN) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM prediction_registry WHERE run_id = 'run-t2'")


def test_finalize_run_requires_prediction(store):
    with pytest.raises(RunWithoutPredictionError):
        store.finalize_run("run-ไม่มี-prediction")
    store.register_prediction("run-t3", _prediction())
    store.finalize_run("run-t3")  # มี record แล้ว = ผ่าน


def test_confidence_bounds_enforced_by_db(store):
    import psycopg

    bad = Prediction(
        claim="c",
        direction="d",
        confidence=1.5,
        measurement="m",
        due_date=date(2026, 8, 1),
        model_version="v",
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        store.register_prediction("run-t4", bad)
