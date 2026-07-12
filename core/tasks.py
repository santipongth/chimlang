"""Celery queue (P4-M3, ตาม D7) — simulation run เป็น async task รองรับหลาย run พร้อมกัน (NFR-03)

รัน worker:  uv run celery -A core.tasks.celery_app worker --pool=solo -l info
(Windows ต้องใช้ --pool=solo หรือ threads; Linux ใช้ default prefork ได้)

Governance: election guard ถูกตรวจ 2 ชั้น — ที่ endpoint ก่อน enqueue (fail fast)
และใน task เอง (ผ่าน _run_dashboard → require_aggregate) กันการยิง task ตรงข้าม API
"""

from celery import Celery

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
)


@celery_app.task(name="chimlang.whatif_dashboard")
def whatif_dashboard_task(subject: str, granularity: str, agents: int) -> dict:
    """รัน what-if multiverse เต็มรูปใน worker — คืน dashboard dict"""
    from api.app import _run_dashboard  # import ใน task กัน circular ตอน API โหลด tasks

    return _run_dashboard(subject, granularity, agents).to_dict()


@celery_app.task(name="chimlang.check_watchlists")
def check_watchlists_task() -> dict:
    """P5-M5 — ไล่ตรวจ watchlist ที่ถึงรอบตาม cadence แล้วสร้าง alert/webhook

    ตัวหนึ่งพังไม่หยุดตัวอื่น (best-effort ราย watchlist) — คืนสรุปจำนวนที่ตรวจ/alert
    """
    from governance.watchlist import WatchlistStore, check_watchlist, default_runner

    store = WatchlistStore(_settings.postgres_url)
    store.setup()
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
}
