"""Prediction Experience: binary resolution + evidence, legacy partial read compatibility."""

from datetime import UTC, date, datetime, timedelta

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
            source_kind="user",
        ),
    )
    with psycopg.connect(DSN) as conn:
        return conn.execute(
            "SELECT id FROM prediction_registry WHERE run_id = %s ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()[0]


def _resolution_kwargs() -> dict:
    return {
        "resolver": "test",
        "observed_at": datetime.now(UTC),
        "evidence_url": "https://example.org/outcome",
        "evidence_name": "หลักฐานผลจริง",
    }


def _api_resolution(outcome: str = "true") -> dict:
    return {
        "outcome": outcome,
        "observed_at": datetime.now(UTC).isoformat(),
        "evidence_url": "https://example.org/outcome",
        "evidence_name": "หลักฐานผลจริง",
        "note": "ทดสอบ",
    }


def test_partial_outcome_cannot_be_created(store):
    pid = _register(store, "run-p5m3-partial", confidence=0.8)
    with pytest.raises(ValueError, match="binary"):
        store.resolve_prediction(pid, outcome=0.5, **_resolution_kwargs())


def test_bool_outcome_still_works(store):
    pid = _register(store, "run-p5m3-bool", confidence=0.7)
    assert store.resolve_prediction(pid, outcome=True, **_resolution_kwargs()) == pytest.approx(
        0.09
    )


def test_invalid_outcome_value_rejected(store):
    pid = _register(store, "run-p5m3-badval", confidence=0.5)
    with pytest.raises(ValueError):
        store.resolve_prediction(pid, outcome=0.3, **_resolution_kwargs())


def test_resolve_api_full_cycle_and_conflict(client, store):
    pid = _register(store, "run-p5m3-api", confidence=0.6)
    r = client.post(f"/predictions/{pid}/resolve", json=_api_resolution("true"))
    assert r.status_code == 200
    assert r.json()["brier"] == pytest.approx((0.6 - 1.0) ** 2)
    # resolve ซ้ำ = แก้ผลย้อนหลัง → 409 (TRUST-01)
    r2 = client.post(f"/predictions/{pid}/resolve", json=_api_resolution("false"))
    assert r2.status_code == 409


def test_resolve_api_unknown_id_404_and_bad_outcome_422(client, store):
    assert (
        client.post("/predictions/99999999/resolve", json=_api_resolution("true")).status_code
        == 404
    )
    pid = _register(store, "run-p5m3-badout", confidence=0.5)
    assert (
        client.post(f"/predictions/{pid}/resolve", json=_api_resolution("maybe")).status_code == 422
    )


def test_resolve_requires_run_permission(client, store, monkeypatch):
    monkeypatch.setattr(
        auth_mod,
        "get_settings",
        lambda **kw: Settings(auth_enabled=True, api_keys=KEYS, _env_file=None),
    )
    pid = _register(store, "run-p5m3-rbac", confidence=0.5)
    # viewer ไม่มีสิทธิ์ RUN → 403 | ไม่มีคีย์ → 401
    assert (
        client.post(f"/predictions/{pid}/resolve", json=_api_resolution("true")).status_code == 401
    )
    assert (
        client.post(
            f"/predictions/{pid}/resolve",
            json=_api_resolution("true"),
            headers={"X-API-Key": "view-key"},
        ).status_code
        == 403
    )
    # analyst ทำได้
    assert (
        client.post(
            f"/predictions/{pid}/resolve",
            json=_api_resolution("true"),
            headers={"X-API-Key": "ana-key"},
        ).status_code
        == 200
    )


def test_calibration_json_shape_and_test_domain_filtered(client, store):
    from datetime import date

    pid = _register(store, "run-p5m3-shape", confidence=0.9)
    store.resolve_prediction(pid, outcome=True, **_resolution_kwargs())
    data = client.get("/calibration.json").json()
    assert set(data) >= {
        "overall_brier",
        "resolved_total",
        "domains",
        "trend",
        "items",
        "due",
        "upcoming",
        "reliability",
        "confidence_histogram",
    }
    # UI/API กรอง domain 'ทดสอบ%' ออก (ขยะ test — registry ลบไม่ได้จึงกรองชั้นอ่าน)
    assert all(not d["domain"].startswith("ทดสอบ") for d in data["domains"])
    assert all(i["prediction_id"] != pid for i in data["items"])
    # แต่ชั้น store (include_test default) ยังเห็น prediction ใหม่ครบ
    detail = store.calibration_detail(date.today())
    dom = next(d for d in detail["domains"] if d["domain"] == "ทดสอบ-p5m3")
    assert dom["happened"] >= 1
    item = next(i for i in detail["items"] if i["prediction_id"] == pid)
    assert item["outcome_value"] == 1.0
    assert item["evidence_url"] == "https://example.org/outcome"
