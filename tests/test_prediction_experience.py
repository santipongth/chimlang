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


@pytest.fixture()
def eager_client() -> TestClient:
    """TestClient ที่รัน Celery task แบบ eager — จำเป็นสำหรับเส้นทาง enqueue จริง"""
    from core.tasks import celery_app

    old_eager = celery_app.conf.task_always_eager
    old_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    with TestClient(app) as test_client:
        yield test_client
    celery_app.conf.task_always_eager = old_eager
    celery_app.conf.task_eager_propagates = old_propagates


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


def test_three_seed_validation_completes_for_fabric_run_with_stored_20_rounds(eager_client):
    """Regression: fabric เก็บ rounds=20 ใน DB แต่ RunBody จำกัด <= 10 —
    เดิม POST /runs/{id}/validate จึง 500 ทุกครั้งสำหรับ fabric run"""
    body = {
        "engine": "fabric",
        "subject": f"ตรวจซ้ำความเสถียรผลจำลอง {uuid4().hex[:8]}",
        "agents": 12,
    }
    created = eager_client.post(
        "/runs/async", json=body, headers={"Idempotency-Key": f"validate-{uuid4().hex[:12]}"}
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    child_ids: list[str] = []
    try:
        parent = eager_client.get(f"/runs/{run_id}.json").json()
        assert parent["status"] == "complete"
        queued = eager_client.post(f"/runs/{run_id}/validate")
        assert queued.status_code == 200, queued.text
        report = eager_client.get(f"/runs/{run_id}/validation").json()
        child_ids = [c["run_id"] for c in report["children"]]
        assert report["completed"] == 3
        assert report["status"] == "complete"
        base_seed = int(parent["seed"])
        assert sorted(c["seed"] for c in report["children"]) == [
            base_seed + 1,
            base_seed + 2,
            base_seed + 3,
        ]
        assert all(c["value"] is not None for c in report["children"])
        assert report["sign_agreement"] is not None
        # เรียก validate ซ้ำ = คืนรายงานเดิม ไม่ queue ลูกเพิ่ม
        again = eager_client.post(f"/runs/{run_id}/validate").json()
        assert {c["run_id"] for c in again["children"]} == set(child_ids)
    finally:
        store = RunStore(DSN)
        for child_id in child_ids:
            store.delete(child_id)
        store.delete(run_id)


def test_rerun_children_do_not_pollute_three_seed_validation(eager_client):
    """Regression: retry/rerun ก็ตั้ง parent_run_id เหมือนกัน — เดิมลูก rerun ถูกนับเป็น
    รายงาน validation ปลอม และทำให้ validate ไม่ queue ลูก 3 seed จริงเลย"""
    parent_id = _complete_run()
    store = RunStore(DSN)
    rerun_child = f"prediction-experience-{uuid4()}"
    store.create(
        run_id=rerun_child,
        engine="fabric",
        subject="ลูกที่เกิดจาก rerun ไม่ใช่ validation",
        domain="ทดสอบ",
        agents=20,
        rounds=20,
        seed=18,
        config={"parent_run_id": parent_id},
        parent_run_id=parent_id,
    )
    store.finish(rerun_child, {"result_kind": "simulation_finding", "cost_usd": 0})
    child_ids: list[str] = []
    try:
        # ลูก rerun ต้องไม่โผล่ในรายงาน validation
        empty = eager_client.get(f"/runs/{parent_id}/validation").json()
        assert empty["children"] == []
        # และต้องไม่ block การ queue ลูก validation จริง 3 ชุด
        queued = eager_client.post(f"/runs/{parent_id}/validate")
        assert queued.status_code == 200, queued.text
        report = eager_client.get(f"/runs/{parent_id}/validation").json()
        child_ids = [c["run_id"] for c in report["children"]]
        assert report["completed"] == 3
        assert rerun_child not in child_ids
    finally:
        for child_id in child_ids:
            store.delete(child_id)
        store.delete(rerun_child)
        store.delete(parent_id)


def test_validate_requeues_only_missing_seeds_after_partial_enqueue(eager_client):
    """Regression: ถ้า enqueue ล้มกลางคัน (เช่น worker หลุดหลังลูกแรก) การกด validate ซ้ำ
    ต้อง queue เฉพาะ seed ที่ขาด ไม่ใช่คืนรายงาน incomplete ค้างตลอดไป"""
    parent_id = _complete_run()  # seed 17
    store = RunStore(DSN)
    partial_child = f"prediction-experience-{uuid4()}"
    store.create(
        run_id=partial_child,
        engine="fabric",
        subject="ลูก validation ที่รอดจากรอบ enqueue ที่ล้ม",
        domain="ทดสอบ",
        agents=20,
        rounds=20,
        seed=18,  # base 17 + offset 1
        config={"parent_run_id": parent_id, "run_kind": "three_seed_validation"},
        parent_run_id=parent_id,
    )
    store.finish(partial_child, {"brief": {"headline_range": [-0.1, 0.1]}, "cost_usd": 0})
    new_children: list[str] = []
    try:
        queued = eager_client.post(f"/runs/{parent_id}/validate")
        assert queued.status_code == 200, queued.text
        report = eager_client.get(f"/runs/{parent_id}/validation").json()
        new_children = [c["run_id"] for c in report["children"] if c["run_id"] != partial_child]
        assert report["completed"] == 3
        assert sorted(int(c["seed"]) for c in report["children"]) == [18, 19, 20]
        assert partial_child in {c["run_id"] for c in report["children"]}
    finally:
        for child_id in new_children:
            store.delete(child_id)
        store.delete(partial_child)
        store.delete(parent_id)
