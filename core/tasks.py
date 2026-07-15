"""Celery queue (P4-M3, ตาม D7) — simulation run เป็น async task รองรับหลาย run พร้อมกัน (NFR-03)

รัน worker:  uv run celery -A core.tasks.celery_app worker --pool=solo -l info
(Windows ต้องใช้ --pool=solo หรือ threads; Linux ใช้ default prefork ได้)

Governance: election guard ถูกตรวจ 2 ชั้น — ที่ endpoint ก่อน enqueue (fail fast)
และใน task เอง (ผ่าน _run_dashboard → require_aggregate) กันการยิง task ตรงข้าม API
"""

from contextlib import contextmanager, nullcontext
from threading import Event, Thread

from celery import Celery, signals

from core.config import get_settings

_settings = get_settings()

celery_app = Celery("chimlang", broker=_settings.redis_url, backend=_settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600 * 24,
    broker_connection_retry_on_startup=False,
    broker_transport_options={"max_retries": 1, "socket_connect_timeout": 3},
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_publish_retry=True,
    task_publish_retry_policy={"max_retries": 3, "interval_start": 0, "interval_step": 0.5},
    task_routes={
        "chimlang.whatif_dashboard": {"queue": "fabric"},
        "chimlang.check_watchlists": {"queue": "maintenance"},
        "chimlang.detect_stale_runs": {"queue": "maintenance"},
    },
)


@signals.worker_process_init.connect
def _worker_schema_check(**_kwargs) -> None:
    from core.db import require_schema

    require_schema(_settings.postgres_url)


@contextmanager
def _heartbeat(run_id: str, interval_s: float = 15.0):
    """Keep long LLM rounds observable without blocking task progress."""
    from core.runstore import RunStore

    stop = Event()
    store = RunStore(_settings.postgres_url)

    def beat() -> None:
        while not stop.wait(interval_s):
            try:
                store.heartbeat(run_id)
            except Exception:
                pass

    thread = Thread(target=beat, name=f"heartbeat-{run_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1)


@celery_app.task(name="chimlang.whatif_dashboard")
def whatif_dashboard_task(subject: str, granularity: str, agents: int) -> dict:
    """รัน what-if multiverse เต็มรูปใน worker — คืน dashboard dict"""
    from api.app import _run_dashboard  # import ใน task กัน circular ตอน API โหลด tasks

    return _run_dashboard(subject, granularity, agents).to_dict()


@celery_app.task(name="chimlang.persistent_run")
def persistent_run_task(
    body: dict, actor: str, election_verified: bool = False, run_id: str | None = None
) -> dict:
    """สร้าง persistent run ใน worker — ใช้ code path เดียวกับ POST /runs เพื่อไม่ข้าม governance."""
    from api.app import RunBody, _run_create_impl
    from governance.rbac import Principal, Role

    role = Role.ADMIN if election_verified else Role.ANALYST
    principal = Principal(user_id=actor, role=role, election_verified=election_verified)
    if run_id:
        from core.runstore import RunStore

        store = RunStore(_settings.postgres_url)
        detail = store.get(run_id)
        if detail["status"] in {"complete", "running", "canceled"}:
            return {
                "run_id": run_id,
                "engine": detail["engine"],
                "agents": detail["agents"],
                "idempotent": True,
                "status": detail["status"],
            }
    with _heartbeat(run_id) if run_id else nullcontext():
        try:
            return _run_create_impl(
                RunBody(**body), principal=principal, run_id=run_id, precreated=bool(run_id)
            )
        except Exception as exc:
            if run_id and getattr(exc, "status_code", None) == 409:
                current = RunStore(_settings.postgres_url).get(run_id)
                return {
                    "run_id": run_id,
                    "engine": current["engine"],
                    "agents": current["agents"],
                    "idempotent": True,
                    "status": current["status"],
                }
            raise


@celery_app.task(name="chimlang.check_watchlists")
def check_watchlists_task() -> dict:
    """P5-M5 — ไล่ตรวจ watchlist ที่ถึงรอบตาม cadence แล้วสร้าง alert/webhook

    ตัวหนึ่งพังไม่หยุดตัวอื่น (best-effort ราย watchlist) — คืนสรุปจำนวนที่ตรวจ/alert
    """
    from governance.watchlist import WatchlistStore, check_watchlist, default_runner

    store = WatchlistStore(_settings.postgres_url)
    checked, alerts, failed = 0, 0, 0
    for w in store.due():
        try:
            alerts += len(check_watchlist(store, w, runner=default_runner))
            checked += 1
        except Exception:
            failed += 1  # watchlist เดียวพังห้ามลากทั้งคิว
    return {"checked": checked, "alerts": alerts, "failed": failed}


# Celery beat: ปลุกทุกชั่วโมง (cadence จริงคุมใน WatchlistStore.due())
# รัน beat: uv run celery -A core.tasks.celery_app beat -l info
celery_app.conf.beat_schedule = {
    "check-watchlists-hourly": {"task": "chimlang.check_watchlists", "schedule": 3600.0},
    "detect-stale-runs": {"task": "chimlang.detect_stale_runs", "schedule": 60.0},
}


@celery_app.task(name="chimlang.detect_stale_runs")
def detect_stale_runs_task() -> dict:
    from core.runstore import RunStore

    stale = RunStore(_settings.postgres_url).mark_stale()
    return {"stale": stale, "count": len(stale)}
