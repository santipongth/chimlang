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
        json={
            "engine": "fabric",
            "subject": "readiness scenario",
            "agents": 20,
            "population_acknowledged": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["can_run"] is True
    assert body["cost"]["estimated_usd"] == 0
    assert any(c["id"] == "pii" and c["status"] == "pass" for c in body["checks"])


def test_run_readiness_blocks_exceeded_monthly_budget(client, monkeypatch):
    import core.run_quality as quality
    from core.config import Settings

    monkeypatch.setattr(quality, "spent_this_month", lambda dsn: 10.0)
    monkeypatch.setattr(quality, "effective_monthly_cap", lambda: 5.0)
    # CI tier "mocked" ไม่มี .env/DB — pin model ให้ cost estimate ไปถึง monthly check ได้
    # (โจทย์ของ test คือ monthly cap block ไม่ใช่ pricing fail-closed ซึ่งมี test แยกอยู่แล้ว)
    monkeypatch.setattr(
        quality,
        "effective_llm_settings",
        lambda: Settings(
            llm_model_crowd="qwen/qwen3.5-flash-02-23",
            llm_model_analyst="qwen/qwen3-235b-a22b-2507",
            _env_file=None,
        ),
    )
    r = client.post(
        "/runs/readiness",
        json={
            "engine": "debate",
            "subject": "monthly budget readiness",
            "agents": 10,
            "population_acknowledged": True,
            "retrieval_mode": "bm25",
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["can_run"] is False
    monthly = next(c for c in body["checks"] if c["id"] == "monthly_budget")
    assert monthly["status"] == "block"
    assert body["cost"]["monthly_spent_usd"] == 10.0


def test_run_readiness_persona_fit_advisory(client):
    # ADR-0028: debate+citizen → persona_fit warn (ไม่ block); analyst → pass; fabric → ไม่มี
    citizen = client.post(
        "/runs/readiness",
        json={"engine": "debate", "subject": "สเปนเป็นแชมป์ฟุตบอลโลก 2026", "agents": 10},
    ).json()
    pf = next(c for c in citizen["checks"] if c["id"] == "persona_fit")
    assert pf["status"] == "warn"

    analyst = client.post(
        "/runs/readiness",
        json={
            "engine": "debate",
            "subject": "สเปนเป็นแชมป์ฟุตบอลโลก 2026",
            "agents": 10,
            "discourse_register": "analyst",
        },
    ).json()
    pf2 = next(c for c in analyst["checks"] if c["id"] == "persona_fit")
    assert pf2["status"] == "pass"

    fabric = client.post(
        "/runs/readiness",
        json={"engine": "fabric", "subject": "readiness scenario", "agents": 20},
    ).json()
    assert not any(c["id"] == "persona_fit" for c in fabric["checks"])


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
        json={
            "engine": "fabric",
            "subject": "ทดสอบ persistent run ผ่าน queue",
            "agents": 20,
            "population_acknowledged": True,
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "complete"
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
    from core import tasks
    from core.runstore import RunStore
    from core.tasks import persistent_run_task

    class _QueuedResult:
        id = "queued-job-1"
        status = "PENDING"

    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(tasks, "worker_available", lambda **_kwargs: True)
    monkeypatch.setattr(persistent_run_task, "apply_async", lambda *args, **kwargs: _QueuedResult())
    try:
        r = client.post(
            "/runs/async",
            json={
                "engine": "fabric",
                "subject": "ทดสอบ queued row",
                "agents": 20,
                "population_acknowledged": True,
            },
        )
    finally:
        celery_app.conf.task_always_eager = old_eager
    assert r.status_code == 202
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
    from core import tasks
    from core.runstore import RunStore
    from core.tasks import persistent_run_task

    class _QueuedResult:
        id = "cancel-job-1"
        status = "PENDING"

    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(tasks, "worker_available", lambda **_kwargs: True)
    monkeypatch.setattr(persistent_run_task, "apply_async", lambda *args, **kwargs: _QueuedResult())
    try:
        r = client.post(
            "/runs/async",
            json={
                "engine": "fabric",
                "subject": "ทดสอบ cancel queued",
                "agents": 20,
                "population_acknowledged": True,
            },
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
def test_async_run_rejects_before_persist_when_worker_is_offline(client, monkeypatch):
    from core import tasks
    from core.runstore import RunStore

    subject = "ทดสอบปฏิเสธเมื่อ worker offline " + uuid4().hex[:8]
    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(tasks, "worker_available", lambda **_kwargs: False)
    try:
        response = client.post(
            "/runs/async",
            json={
                "engine": "fabric",
                "subject": subject,
                "agents": 20,
                "population_acknowledged": True,
            },
        )
    finally:
        celery_app.conf.task_always_eager = old_eager
    assert response.status_code == 503
    assert "worker ไม่พร้อม" in response.json()["detail"]
    assert RunStore(DSN).list_runs(search=subject) == []


@needs_pg
def test_async_run_reuses_accepted_idempotency_key_when_worker_goes_offline(client, monkeypatch):
    from core import tasks
    from core.runstore import RunStore
    from core.tasks import persistent_run_task

    class _QueuedResult:
        id = "task-worker-offline-reuse"

    suffix = uuid4().hex[:8]
    key = f"worker-reuse-{suffix}"
    body = {
        "engine": "fabric",
        "subject": f"ทดสอบ idempotency worker offline {suffix}",
        "agents": 20,
        "population_acknowledged": True,
    }
    old_eager = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(tasks, "worker_available", lambda **_kwargs: True)
    monkeypatch.setattr(persistent_run_task, "apply_async", lambda *args, **kwargs: _QueuedResult())
    try:
        first = client.post("/runs/async", json=body, headers={"Idempotency-Key": key})
        assert first.status_code == 202
        monkeypatch.setattr(tasks, "worker_available", lambda **_kwargs: False)
        reused = client.post("/runs/async", json=body, headers={"Idempotency-Key": key})
    finally:
        celery_app.conf.task_always_eager = old_eager
    assert reused.status_code == 202
    assert reused.json()["reused"] is True
    assert reused.json()["run_id"] == first.json()["run_id"]
    RunStore(DSN).delete(first.json()["run_id"])


def test_worker_available_requires_a_fresh_valid_heartbeat(monkeypatch):
    import redis

    from core import tasks

    class _RedisClient:
        value: str | None = None

        def get(self, _key):
            return self.value

        def close(self):
            return None

    client = _RedisClient()
    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: client)
    monkeypatch.setattr(tasks, "time", lambda: 100.0)

    for value, expected in (
        (None, False),
        ("invalid", False),
        ("79.9", False),
        ("80", True),
        ("101", False),
    ):
        client.value = value
        assert tasks.worker_available() is expected


def test_worker_available_can_require_live_celery_control_reply(monkeypatch):
    import redis

    from core import tasks

    class _RedisClient:
        def get(self, _key):
            return "100"

        def close(self):
            return None

    monkeypatch.setattr(redis.Redis, "from_url", lambda *args, **kwargs: _RedisClient())
    monkeypatch.setattr(tasks, "time", lambda: 100.0)
    monkeypatch.setattr(tasks.celery_app.control, "ping", lambda timeout: [])
    assert tasks.worker_available(verify_control=True) is False

    monkeypatch.setattr(
        tasks.celery_app.control,
        "ping",
        lambda timeout: [{"celery@worker": {"ok": "pong"}}],
    )
    assert tasks.worker_available(verify_control=True) is True
