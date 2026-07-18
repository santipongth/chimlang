from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.app import _validation_report, app
from core.runstore import RunStore
from governance.store import GovernanceStore, Prediction, SimulationFinding

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


@pytest.fixture(scope="module", autouse=True)
def database_ready():
    try:
        GovernanceStore(DSN).setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _complete_run() -> str:
    run_id = f"prediction-experience-{uuid4()}"
    store = RunStore(DSN)
    store.create(
        run_id=run_id,
        engine="fabric",
        subject="ทดสอบ prediction experience",
        domain="ทดสอบ",
        agents=20,
        rounds=20,
        seed=17,
        config={},
    )
    GovernanceStore(DSN).register_finding(
        run_id,
        SimulationFinding(
            summary="finding จากโลกจำลอง",
            metrics={"delta": 0.1},
            provenance={"run_id": run_id},
            model_version="test",
        ),
    )
    store.finish(run_id, {"result_kind": "simulation_finding", "cost_usd": 0})
    return run_id


def test_explicit_prediction_and_evidence_resolution(client):
    run_id = _complete_run()
    try:
        created = client.post(
            f"/runs/{run_id}/predictions",
            json={
                "claim": "ประกาศจะมีผลบังคับใช้ภายในเดือนหน้า",
                "probability": 0.7,
                "measurement": "ตรวจประกาศในราชกิจจานุเบกษา",
                "due_date": (date.today() + timedelta(days=30)).isoformat(),
                "forecast_type": "binary",
            },
        )
        assert created.status_code == 200
        prediction = created.json()["predictions"][-1]
        assert prediction["source_kind"] == "user"
        resolved = client.post(
            f"/predictions/{prediction['prediction_id']}/resolve",
            json={
                "outcome": "true",
                "observed_at": datetime.now(UTC).isoformat(),
                "evidence_url": "https://example.org/official-result",
                "evidence_name": "ประกาศผลอย่างเป็นทางการ",
                "note": "ตรวจด้วยคน",
            },
        )
        assert resolved.status_code == 200
        detail = client.get(f"/runs/{run_id}/predictions").json()
        assert detail["predictions"][-1]["resolution"]["evidence_name"]
    finally:
        RunStore(DSN).delete(run_id)


def test_legacy_partial_is_readable_but_excluded_from_primary_calibration():
    gov = GovernanceStore(DSN)
    run_id = f"legacy-partial-{uuid4()}"
    gov.register_prediction(
        run_id,
        Prediction(
            claim="legacy partial",
            direction="เกิดขึ้น",
            confidence=0.8,
            measurement="legacy",
            due_date=date.today(),
            model_version="legacy",
            domain="legacy-test",
        ),
    )
    with psycopg.connect(DSN) as conn:
        prediction_id = conn.execute(
            "SELECT id FROM prediction_registry WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO prediction_resolution "
            "(prediction_id, outcome, outcome_value, brier, resolver, note) "
            "VALUES (%s, NULL, 0.5, 0.09, 'legacy', 'compatibility row')",
            (prediction_id,),
        )
    # legacy row ต้องไม่ถูกนับใน primary calibration (calibration_summary กรอง source_kind='legacy')
    assert all(row.domain != "legacy-test" for row in gov.calibration_summary())
    # แต่แถว partial เดิมยังอ่านได้ตรงๆ จาก registry/resolution (append-only ไม่ถูกลบ)
    with psycopg.connect(DSN) as conn:
        value = conn.execute(
            "SELECT outcome_value FROM prediction_resolution WHERE prediction_id = %s",
            (prediction_id,),
        ).fetchone()[0]
    assert float(value) == 0.5


def test_synthesis_revision_is_append_only():
    run_id = _complete_run()
    store = RunStore(DSN)
    try:
        revision_id = store.add_synthesis_revision(
            run_id,
            kind="mechanical",
            synthesis={"summary": "snapshot"},
            metrics={"posts_ok": 2},
            parser_mode="deterministic",
        )
        with psycopg.connect(DSN) as conn:
            with pytest.raises(psycopg.errors.RaiseException):
                conn.execute(
                    "UPDATE run_synthesis_revisions SET kind = 'analyst' WHERE id = %s",
                    (revision_id,),
                )
    finally:
        store.delete(run_id)


def test_event_reconnect_replays_ids_and_terminal_event(client):
    run_id = _complete_run()
    try:
        events = RunStore(DSN).events_after(run_id, 0)
        assert [e["id"] for e in events] == sorted(e["id"] for e in events)
        after = events[0]["id"]
        replay = RunStore(DSN).events_after(run_id, after)
        assert replay and all(e["id"] > after for e in replay)
        with client.stream("GET", f"/runs/{run_id}/events/stream?after_id={after}") as response:
            assert response.status_code == 200
            body = "".join(response.iter_text())
        assert "event: run_event" in body and "completed" in body
    finally:
        RunStore(DSN).delete(run_id)


def test_validation_report_separates_stability_from_confidence():
    children = [
        {
            "run_id": f"child-{seed}",
            "engine": "debate",
            "seed": seed,
            "status": "complete",
            "error": None,
            "payload": {
                "metrics": {
                    "per_round_avg_stance": [stance],
                    "posts_ok": 9,
                    "posts_failed": 1,
                },
                "synthesis": {"summary": "กลุ่มส่วนใหญ่เห็นด้วย แต่ยังมีความเสี่ยง"},
                "cost_usd": 0.01,
            },
        }
        for seed, stance in ((1, 0.2), (2, 0.3), (3, -0.1))
    ]
    report = _validation_report("parent", children)
    assert report["completed"] == 3
    assert report["sign_agreement"] == pytest.approx(2 / 3)
    assert report["agent_failure_rate"] == pytest.approx(0.1)
    assert [child["value"] for child in report["children"]] == [0.2, 0.3, -0.1]
    assert "analyst confidence" in report["note"]
