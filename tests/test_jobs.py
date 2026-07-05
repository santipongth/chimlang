"""tests P4-M3: queue endpoint (eager mode), election guard ก่อน enqueue, cap agents"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.tasks import celery_app


@pytest.fixture(autouse=True)
def eager_celery():
    """โหมด test: รัน task ทันทีในโปรเซสเดียว — ไม่ต้องมี broker/worker จริง"""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_submit_job_runs_and_returns_result(client):
    r = client.post("/jobs/whatif", json={"subject": "แคมเปญราคาสินค้า", "agents": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCESS" and body["job_id"]
    assert "brief" in body["result"]  # ได้ dashboard เต็มจาก task
    assert body["result"]["brief"]["fragility_index"] >= 0


def test_election_guard_before_enqueue(client):
    r = client.post(
        "/jobs/whatif",
        json={"subject": "จำลองผลเลือกตั้งผู้ว่าฯ", "granularity": "individual"},
    )
    assert r.status_code == 403  # ถูกปัดตกก่อนเข้าคิว (fail fast)


def test_agents_clamped_to_cap(client):
    # ขอ 999999 → ต้องถูก clamp ที่ cap ไม่ใช่ error (BudgetGuard/cap คุมจริง)
    r = client.post("/jobs/whatif", json={"subject": "ทดสอบ cap", "agents": 999999})
    assert r.status_code == 200


def test_task_itself_enforces_governance():
    """ยิง task ตรง (ข้าม API) — require_aggregate ใน _run_dashboard ต้องยังกันได้"""
    from core.tasks import whatif_dashboard_task
    from governance.election import ElectionModeError

    with pytest.raises(ElectionModeError):
        whatif_dashboard_task.apply(args=("เลือกตั้ง ส.ส.", "individual", 20), throw=True).get()
