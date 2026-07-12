"""tests P5-M3: Calibration UI backend — partial=0.5, append-only ผ่าน API, RBAC"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import api.auth as auth_mod
from api.app import app
from core.config import Settings
from governance.store import GovernanceStore, Prediction

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"
KEYS = "adm-key:boss:admin:verified,ana-key:ana:analyst,view-key:v:viewer"


@pytest.fixture(scope="module")
def store() -> GovernanceStore:
    s = GovernanceStore(DSN)
    try:
        s.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    return s


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _register(store: GovernanceStore, run_id: str, confidence: float) -> int:
    import psycopg

    store.register_prediction(
        run_id,
        Prediction(
            claim="claim ทดสอบ P5-M3",
            direction="เกิดขึ้น",
            confidence=confidence,
            measurement="เทียบผลจริง",
            due_date=date.today() - timedelta(days=1),
            model_version="test",
            domain="ทดสอบ-p5m3",
        ),
    )
    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "SELECT id FROM prediction_registry WHERE run_id = %s ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()[0]


def test_partial_outcome_is_half_in_brier(store):
    # partial = 0.5 → Brier = (0.8 − 0.5)² = 0.09 (SwarmSight ก็นิยามแบบนี้)
    pid = _register(store, "run-p5m3-partial", confidence=0.8)
    brier = store.resolve_prediction(pid, outcome=0.5, resolver="test")
    assert brier == pytest.approx(0.09)


def test_bool_outcome_still_works(store):
    pid = _register(store, "run-p5m3-bool", confidence=0.7)
    assert store.resolve_prediction(pid, outcome=True, resolver="test") == pytest.approx(0.09)


def test_invalid_outcome_value_rejected(store):
    pid = _register(store, "run-p5m3-badval", confidence=0.5)
    with pytest.raises(ValueError):
        store.resolve_prediction(pid, outcome=0.3, resolver="test")


def test_resolve_api_full_cycle_and_conflict(client, store):
    pid = _register(store, "run-p5m3-api", confidence=0.6)
    r = client.post(f"/predictions/{pid}/resolve", json={"outcome": "partial", "note": "ทดสอบ"})
    assert r.status_code == 200
    assert r.json()["brier"] == pytest.approx((0.6 - 0.5) ** 2)
    # resolve ซ้ำ = แก้ผลย้อนหลัง → 409 (TRUST-01)
    r2 = client.post(f"/predictions/{pid}/resolve", json={"outcome": "false", "note": "แก้ผล"})
    assert r2.status_code == 409


def test_resolve_api_unknown_id_404_and_bad_outcome_422(client, store):
    assert client.post("/predictions/99999999/resolve", json={"outcome": "true"}).status_code == 404
    pid = _register(store, "run-p5m3-badout", confidence=0.5)
    assert client.post(f"/predictions/{pid}/resolve", json={"outcome": "maybe"}).status_code == 422


def test_resolve_requires_run_permission(client, store, monkeypatch):
    monkeypatch.setattr(
        auth_mod,
        "get_settings",
        lambda **kw: Settings(auth_enabled=True, api_keys=KEYS, _env_file=None),
    )
    pid = _register(store, "run-p5m3-rbac", confidence=0.5)
    # viewer ไม่มีสิทธิ์ RUN → 403 | ไม่มีคีย์ → 401
    assert client.post(f"/predictions/{pid}/resolve", json={"outcome": "true"}).status_code == 401
    assert (
        client.post(
            f"/predictions/{pid}/resolve",
            json={"outcome": "true"},
            headers={"X-API-Key": "view-key"},
        ).status_code
        == 403
    )
    # analyst ทำได้
    assert (
        client.post(
            f"/predictions/{pid}/resolve",
            json={"outcome": "true"},
            headers={"X-API-Key": "ana-key"},
        ).status_code
        == 200
    )


def test_calibration_json_shape(client, store):
    pid = _register(store, "run-p5m3-shape", confidence=0.9)
    store.resolve_prediction(pid, outcome=0.5, resolver="test")
    data = client.get("/calibration.json").json()
    assert set(data) >= {
        "overall_brier",
        "resolved_total",
        "domains",
        "trend",
        "items",
        "due",
        "upcoming",
    }
    dom = next(d for d in data["domains"] if d["domain"] == "ทดสอบ-p5m3")
    assert dom["partial"] >= 1  # นับ ~ แยกจาก ✓/✗ จริง
    item = next(i for i in data["items"] if i["prediction_id"] == pid)
    assert item["outcome_value"] == 0.5
