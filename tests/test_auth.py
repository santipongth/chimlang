"""tests P4-M4: auth ปิด = dev-admin, เปิด = 401/403 ตามสิทธิ์, election เฉพาะ admin verified"""

import pytest
from fastapi.testclient import TestClient

import api.auth as auth_mod
from api.app import app
from api.auth import parse_api_keys
from core.config import Settings
from governance.rbac import Role

KEYS = "adm-key:boss:admin:verified,ana-key:ana:analyst,view-key:v:viewer,adm2:x:admin"


def _auth_on(monkeypatch):
    """เปิด auth โดย monkeypatch get_settings ในโมดูล auth (จุดอ่านเดียว)"""
    monkeypatch.setattr(
        auth_mod,
        "get_settings",
        lambda **kw: Settings(auth_enabled=True, api_keys=KEYS, _env_file=None),
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_parse_api_keys_roles_and_bad_entries():
    keys = parse_api_keys(KEYS + ",broken,also:bad")  # รายการเสียต้องถูกข้าม
    assert keys["adm-key"].role == Role.ADMIN and keys["adm-key"].election_verified
    assert keys["ana-key"].role == Role.ANALYST and not keys["ana-key"].election_verified
    assert keys["adm2"].role == Role.ADMIN and not keys["adm2"].election_verified
    assert "broken" not in keys and "also" not in keys


def test_auth_disabled_dev_mode_allows_all(client):
    assert client.get("/runs.json").status_code in (200, 503)  # ไม่ 401 (dev mode)


def test_auth_enabled_requires_key(client, monkeypatch):
    _auth_on(monkeypatch)
    assert client.get("/dashboard.json", params={"agents": 20}).status_code == 401
    assert (
        client.get(
            "/dashboard.json", params={"agents": 20}, headers={"X-API-Key": "wrong"}
        ).status_code
        == 401
    )
    ok = client.get("/dashboard.json", params={"agents": 20}, headers={"X-API-Key": "ana-key"})
    assert ok.status_code == 200  # analyst มีสิทธิ์ RUN


def test_viewer_cannot_run(client, monkeypatch):
    _auth_on(monkeypatch)
    r = client.get("/dashboard.json", params={"agents": 20}, headers={"X-API-Key": "view-key"})
    assert r.status_code == 403  # viewer ไม่มีสิทธิ์ run (GOV-06)


def test_analyst_cannot_export_pdf(client, monkeypatch):
    _auth_on(monkeypatch)
    r = client.get("/dashboard.pdf", params={"agents": 20}, headers={"X-API-Key": "ana-key"})
    assert r.status_code == 403  # ไม่มีสิทธิ์ export
    ok = client.get("/dashboard.pdf", params={"agents": 20}, headers={"X-API-Key": "adm-key"})
    assert ok.status_code == 200


def test_election_scenario_requires_verified_admin(client, monkeypatch):
    _auth_on(monkeypatch)
    params = {"subject": "จำลองผลเลือกตั้งผู้ว่าฯ", "agents": 20}
    # analyst มี RUN แต่ไม่ใช่ admin verified → 403 แม้ granularity aggregate
    assert (
        client.get("/dashboard.json", params=params, headers={"X-API-Key": "ana-key"}).status_code
        == 403
    )
    # admin ที่ไม่ verified ก็ไม่ได้ (GOV-06)
    assert (
        client.get("/dashboard.json", params=params, headers={"X-API-Key": "adm2"}).status_code
        == 403
    )
    # admin verified เท่านั้น
    assert (
        client.get("/dashboard.json", params=params, headers={"X-API-Key": "adm-key"}).status_code
        == 200
    )


def test_citizen_endpoints_stay_public(client, monkeypatch):
    _auth_on(monkeypatch)
    r = client.post(
        "/citizen/impact.json",
        json={
            "income_band": "15k-30k",
            "region": "ชานเมือง",
            "commute": "รถยนต์ส่วนตัว",
            "occupation": "พนักงานออฟฟิศ",
            "age_band": "31-45",
            "household_size": 2,
        },
    )
    assert r.status_code == 200  # Citizen Mode สาธารณะโดยเจตนา (ไม่ต้องมีคีย์)
