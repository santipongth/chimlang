"""tests P4-M3: queue endpoint (eager mode), election guard ก่อน enqueue, cap agents"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.tasks import celery_app

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม (docker compose up -d)")


@pytest.fixture(autouse=True)
def eager_celery():
    """โหมด test: รัน task ทันทีในโปรเซสเดียว — ไม่ต้องมี broker/worker จริง"""
    old_eager = celery_app.conf.task_always_eager
    old_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = old_eager
    celery_app.conf.task_eager_propagates = old_propagates


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


def test_run_readiness_preflight_for_fabric(client):
    r = client.post(
        "/runs/readiness",
        json={"engine": "fabric", "subject": "readiness scenario", "agents": 20},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["can_run"] is True
    assert body["cost"]["estimated_usd"] == 0
    assert any(c["id"] == "pii" and c["status"] == "pass" for c in body["checks"])


def test_task_itself_enforces_governance():
    """ยิง task ตรง (ข้าม API) — require_aggregate ใน _run_dashboard ต้องยังกันได้"""
    from core.tasks import whatif_dashboard_task
    from governance.election import ElectionModeError

    with pytest.raises(ElectionModeError):
        whatif_dashboard_task.apply(args=("เลือกตั้ง ส.ส.", "individual", 20), throw=True).get()


@needs_pg
def test_submit_persistent_run_async_eager(client):
    r = client.post(
        "/runs/async",
        json={"engine": "fabric", "subject": "ทดสอบ persistent run ผ่าน queue", "agents": 20},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SUCCESS"
    assert body["job_id"]
    rid = body["result"]["run_id"]
    detail = client.get(f"/runs/{rid}.json").json()
    assert detail["status"] == "complete"
    assert detail["payload"]["brief"]["fragility_index"] >= 0
    assert detail["trust_scorecard"]["score"] >= 0
    assert any(c["id"] == "reproducibility" for c in detail["trust_scorecard"]["checks"])
    client.delete(f"/runs/{rid}")


def test_run_job_status_reports_failure(client, monkeypatch):
    class _FailedResult:
        status = "FAILURE"
        result = RuntimeError("worker failed")

        def successful(self):
            return False

        def failed(self):
            return True

    monkeypatch.setattr(celery_app, "AsyncResult", lambda job_id: _FailedResult())
    r = client.get("/run-jobs/job-1")
    assert r.status_code == 200
    assert r.json() == {"job_id": "job-1", "status": "FAILURE", "error": "worker failed"}


@needs_pg
def test_async_run_precreates_queued_row(client, monkeypatch):
    from core.runstore import RunStore
    from core.tasks import persistent_run_task

    class _QueuedResult:
        id = "queued-job-1"
        status = "PENDING"

    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(persistent_run_task, "delay", lambda *args: _QueuedResult())
    try:
        r = client.post(
            "/runs/async",
            json={"engine": "fabric", "subject": "ทดสอบ queued row", "agents": 20},
        )
    finally:
        celery_app.conf.task_always_eager = old_eager
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == "queued-job-1"
    assert body["run_id"]

    store = RunStore(DSN)
    store.setup()
    detail = store.get(body["run_id"])
    assert detail["status"] == "queued"
    assert detail["job_id"] == "queued-job-1"
    assert detail["progress"] == 0
    client.delete(f"/runs/{body['run_id']}")


@needs_pg
def test_cancel_queued_run_updates_status(client, monkeypatch):
    from core.runstore import RunStore
    from core.tasks import persistent_run_task

    class _QueuedResult:
        id = "cancel-job-1"
        status = "PENDING"

    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(persistent_run_task, "delay", lambda *args: _QueuedResult())
    try:
        r = client.post(
            "/runs/async",
            json={"engine": "fabric", "subject": "ทดสอบ cancel queued", "agents": 20},
        )
    finally:
        celery_app.conf.task_always_eager = old_eager
    rid = r.json()["run_id"]
    assert client.post(f"/runs/{rid}/cancel").status_code == 200
    store = RunStore(DSN)
    store.setup()
    assert store.get(rid)["status"] == "canceled"
    assert store.mark_running(rid, "worker received stale task") is False
    assert store.get(rid)["status"] == "canceled"
    client.delete(f"/runs/{rid}")


@needs_pg
def test_resynthesize_run_rebuilds_payload_from_posts(client):
    from core.runstore import RunStore

    rid = f"resynth-{uuid4()}"
    store = RunStore(DSN)
    store.setup()
    store.create(
        run_id=rid,
        engine="debate",
        subject="ทดสอบสรุปใหม่",
        domain="ทั่วไป",
        agents=2,
        rounds=2,
        seed=1,
        config={"live_news": False},
    )
    store.add_posts(
        rid,
        [
            {
                "round_no": 0,
                "agent_idx": 0,
                "segment": "a",
                "content": "เห็นด้วย",
                "stance": 0.4,
                "sentiment": 0.1,
            },
            {
                "round_no": 0,
                "agent_idx": 1,
                "segment": "b",
                "content": "ยังลังเล",
                "stance": 0.0,
                "sentiment": 0.0,
            },
            {
                "round_no": 1,
                "agent_idx": 0,
                "segment": "a",
                "content": "เห็นด้วยมากขึ้น",
                "stance": 0.6,
                "sentiment": 0.2,
            },
            {
                "round_no": 1,
                "agent_idx": 1,
                "segment": "b",
                "content": "เริ่มเห็นด้วย",
                "stance": 0.3,
                "sentiment": 0.1,
            },
        ],
    )
    store.finish(rid, {"synthesis": {"summary": "old"}, "metrics": {}})
    try:
        r = client.post(f"/runs/{rid}/resynthesize")
        assert r.status_code == 200
        detail = client.get(f"/runs/{rid}.json").json()
        assert detail["payload"]["synthesis"]["resynthesized_from_snapshot"] is True
        assert detail["payload"]["metrics"]["posts_ok"] == 4
        assert detail["payload"]["protocol"]["contention_graph"]["nodes"]
        assert detail["payload"]["resynthesized_at"]
    finally:
        client.delete(f"/runs/{rid}")


@needs_pg
def test_refresh_news_updates_debate_payload(client, monkeypatch):
    import simulation.newsdesk as nd
    from core.runstore import RunStore

    monkeypatch.setattr(nd, "effective_news_config", lambda settings: ([], ""))
    rid = f"refresh-news-{uuid4()}"
    store = RunStore(DSN)
    store.setup()
    store.create(
        run_id=rid,
        engine="debate",
        subject="ทดสอบ refresh news",
        domain="ทั่วไป",
        agents=2,
        rounds=1,
        seed=1,
        config={"live_news": True},
    )
    store.finish(
        rid,
        {"synthesis": {"summary": "old"}, "metrics": {}, "news": {"enabled": True, "items": []}},
    )
    try:
        r = client.post(f"/runs/{rid}/refresh-news")
        assert r.status_code == 200
        detail = client.get(f"/runs/{rid}.json").json()
        news = detail["payload"]["news"]
        assert news["enabled"] is True
        assert news["refreshed_at"]
        assert any(
            item["provider"] == "search" and item["status"] == "skipped" for item in news["items"]
        )
    finally:
        client.delete(f"/runs/{rid}")
