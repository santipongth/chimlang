"""tests P5-M5: watchlist store + shift detection + webhook guard + endpoints"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import app
from governance.watchlist import WatchlistStore, check_watchlist
from governance.webhook import fire_webhook

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


@pytest.fixture(scope="module")
def store() -> WatchlistStore:
    s = WatchlistStore(DSN)
    try:
        s.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    return s


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---- webhook guard ----


def test_webhook_rejects_http_and_empty():
    assert fire_webhook("tipping_point", {}, url="http://evil.example/hook") is False
    assert fire_webhook("tipping_point", {}, url="") is False
    assert fire_webhook("tipping_point", {}, url=None) in (True, False)  # จาก env — ไม่ raise


def test_webhook_failure_never_raises(monkeypatch):
    import governance.webhook as wh

    def boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(wh.httpx, "post", boom)
    assert fire_webhook("tipping_point", {"subject": "x"}, url="https://hook.example/x") is False


def test_webhook_success_payload_compatible(monkeypatch):
    import governance.webhook as wh

    sent: dict = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json

    monkeypatch.setattr(wh.httpx, "post", fake_post)
    ok = fire_webhook("consensus_shift", {"subject": "ทดสอบ"}, url="https://hook.example/x")
    assert ok is True
    # ต้องมีทั้ง text (Slack) และ content (Discord)
    assert "text" in sent["json"] and "content" in sent["json"]
    assert sent["json"]["kind"] == "consensus_shift"


# ---- store + cadence ----


def test_store_crud_and_due(store):
    wid = store.create(label="ทดสอบ", subject="หัวข้อทดสอบ watchlist", agents=20, cadence="daily")
    w = store.get(wid)
    assert w.active and w.last_run_at is None
    assert wid in [x.id for x in store.due()]  # ไม่เคยรัน = ถึงรอบทันที

    store.touch_run(wid, 0.05)
    assert wid not in [x.id for x in store.due()]  # เพิ่งรัน = ยังไม่ถึงรอบ
    future = datetime.now(UTC) + timedelta(hours=25)
    assert wid in [x.id for x in store.due(now=future)]  # ผ่าน 25 ชม. = ถึงรอบ daily

    store.set_active(wid, False)
    assert wid not in [x.id for x in store.due(now=future)]  # พักไว้ = ไม่รัน


def test_store_rejects_bad_cadence(store):
    with pytest.raises(ValueError):
        store.create(label="x", subject="y", agents=10, cadence="hourly")


# ---- shift detection (fake runner — ไม่แตะ engine) ----


def test_check_creates_shift_alert_after_threshold(store, monkeypatch):
    import governance.watchlist as wl_mod

    monkeypatch.setattr(wl_mod, "fire_webhook", lambda *a, **kw: False)  # กันยิงจริง
    wid = store.create(label="shift", subject="หัวข้อ shift", agents=20, cadence="daily")

    # รอบแรก: ยังไม่มี last_delta → ไม่มี shift alert
    first = check_watchlist(
        store, store.get(wid), runner=lambda s, n: {"mean_delta": -0.20, "tipping": []}
    )
    assert first == []
    assert store.get(wid).last_delta == pytest.approx(-0.20)

    # รอบสอง: delta ขยับ 0.15 ≥ threshold 0.10 → consensus_shift
    second = check_watchlist(
        store, store.get(wid), runner=lambda s, n: {"mean_delta": -0.05, "tipping": []}
    )
    kinds = [a["kind"] for a in second]
    assert kinds == ["consensus_shift"]
    assert second[0]["shift"] == pytest.approx(0.15)


def test_check_creates_tipping_alert_and_webhook_fail_is_silent(store, monkeypatch):
    import governance.watchlist as wl_mod

    calls = {"n": 0}

    def counting_webhook(*a, **kw):
        calls["n"] += 1
        return False  # webhook ล้มเหลว — สัญญา: in-app alert ต้องบันทึกแล้วก่อนหน้า

    monkeypatch.setattr(wl_mod, "fire_webhook", counting_webhook)
    wid = store.create(label="tip", subject="หัวข้อ tipping", agents=20, cadence="weekly")
    created = check_watchlist(
        store,
        store.get(wid),
        runner=lambda s, n: {
            "mean_delta": 0.0,
            "tipping": [{"round": 3, "before": 0.1, "after": 0.4, "delta": 0.3}],
        },
    )
    assert [a["kind"] for a in created] == ["tipping_point"]
    assert calls["n"] == 1  # ยิง webhook 1 ครั้ง (ผลไม่สำคัญ — best-effort)
    alerts = store.list_alerts(unread_only=True)
    assert any(a["kind"] == "tipping_point" and a["watchlist_id"] == wid for a in alerts)


# ---- endpoints ----


def test_watchlist_endpoints_cycle(client, store):
    r = client.post(
        "/watchlists",
        json={"label": "api-test", "subject": "หัวข้อทดสอบ api", "agents": 20, "cadence": "daily"},
    )
    assert r.status_code == 200
    wid = r.json()["id"]

    data = client.get("/watchlists.json").json()
    assert any(w["id"] == wid for w in data["items"])
    assert "unread" in data and "webhook_configured" in data

    assert client.post(f"/watchlists/{wid}/toggle", params={"active": False}).status_code == 200
    assert not next(w for w in client.get("/watchlists.json").json()["items"] if w["id"] == wid)[
        "active"
    ]

    # run now (กลไกล้วน n=20 — เร็ว) — ไม่ควร error
    client.post(f"/watchlists/{wid}/toggle", params={"active": True})
    assert client.post(f"/watchlists/{wid}/run").status_code == 200

    # mark read ทั้งหมด
    assert client.post("/alerts/read", json={"all": True}).status_code == 200
    assert client.get("/watchlists.json").json()["unread"] == 0


def test_watchlist_run_unknown_id_404(client, store):
    assert client.post("/watchlists/99999999/run").status_code == 404


def test_celery_task_function_runs_eagerly(store, monkeypatch):
    # เรียกฟังก์ชัน task ตรงๆ (eager) — best-effort ราย watchlist ต้องไม่ throw
    import governance.watchlist as wl_mod

    monkeypatch.setattr(wl_mod, "fire_webhook", lambda *a, **kw: False)
    from core.tasks import check_watchlists_task

    result = check_watchlists_task.run()
    assert set(result) == {"checked", "alerts", "failed"}
