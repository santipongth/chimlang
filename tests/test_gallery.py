"""tests P5-M8: public gallery — guard fail-closed (ADR-0004), votes dedup, endpoints"""

import pytest
from fastapi.testclient import TestClient

import api.auth as auth_mod
from api.app import app
from core.config import Settings
from governance.election import ElectionModeError
from governance.gallery import GalleryStore, guard_share, voter_hash
from governance.watermark import WatermarkDisabledError

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"
KEYS = "adm-key:boss:admin:verified,ana-key:ana:analyst,op-key:op:operator"


@pytest.fixture(scope="module")
def store() -> GalleryStore:
    s = GalleryStore(DSN)
    try:
        s.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    return s


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---- guard_share (ADR-0004 fail-closed) ----


def test_guard_blocks_election_scenario():
    with pytest.raises(ElectionModeError):
        guard_share("ผลเลือกตั้งผู้ว่าฯ กทม. รอบหน้า")


def test_guard_blocks_pii_subject():
    with pytest.raises(ValueError, match="GOV-01"):
        guard_share("มาตรการช่วยเหลือ ติดต่อ 081-234-5678")


def test_guard_blocks_when_watermark_disabled(monkeypatch):
    import governance.gallery as gal

    monkeypatch.setattr(
        gal, "get_settings", lambda **kw: Settings(watermark_enabled=False, _env_file=None)
    )
    with pytest.raises(WatermarkDisabledError):
        guard_share("หัวข้อปกติ")


def test_guard_blocks_when_pii_detector_disabled(monkeypatch):
    import governance.gallery as gal

    monkeypatch.setattr(
        gal, "get_settings", lambda **kw: Settings(pii_detector_enabled=False, _env_file=None)
    )
    with pytest.raises(ValueError, match="fail-closed"):
        guard_share("หัวข้อปกติ")


def test_guard_allows_normal_subject():
    guard_share("มาตรการค่าธรรมเนียมรถติด กทม.")


# ---- store: snapshot frozen + votes dedup ----


def test_share_snapshot_and_votes_dedup(store):
    payload = {"brief": {"lines": []}, "scenarios": [], "หมายเหตุ": "snapshot ทดสอบ"}
    token = store.share(subject="หัวข้อทดสอบ gallery", agents=20, payload=payload, created_by="test")
    item = store.get(token)
    assert item.payload == payload  # frozen — เท่าที่แชร์เป๊ะ
    assert item.watermark["label"] and "not_field_poll" in item.watermark["labels"]

    # คนเดียวกันโหวตซ้ำ = เปลี่ยนเสียง ไม่ใช่เพิ่มเสียง
    v1 = store.vote(token, "agree", voter_hash("1.2.3.4", "ua"))
    assert v1["agree"] == 1
    v2 = store.vote(token, "disagree", voter_hash("1.2.3.4", "ua"))
    assert v2 == {"agree": 0, "disagree": 1}
    # คนใหม่ = เพิ่มเสียงจริง
    v3 = store.vote(token, "agree", voter_hash("5.6.7.8", "ua2"))
    assert v3 == {"agree": 1, "disagree": 1}

    store.unshare(token)
    assert all(i.share_token != token for i in store.list_public())
    with pytest.raises(ValueError):
        store.vote(token, "agree", voter_hash("9.9.9.9", "ua"))  # ถอนแล้วโหวตไม่ได้


def test_voter_hash_not_reversible_and_stable():
    h = voter_hash("10.0.0.1", "Mozilla")
    assert h == voter_hash("10.0.0.1", "Mozilla") and "10.0.0.1" not in h


# ---- endpoints ----


def test_share_requires_export_permission(client, store, monkeypatch):
    monkeypatch.setattr(
        auth_mod,
        "get_settings",
        lambda **kw: Settings(auth_enabled=True, api_keys=KEYS, _env_file=None),
    )
    body = {"subject": "หัวข้อ rbac gallery", "agents": 20}
    # analyst ไม่มี EXPORT → 403 | ไม่มีคีย์ → 401 | operator แชร์ได้
    assert client.post("/gallery/share", json=body).status_code == 401
    assert (
        client.post("/gallery/share", json=body, headers={"X-API-Key": "ana-key"}).status_code
        == 403
    )
    r = client.post("/gallery/share", json=body, headers={"X-API-Key": "op-key"})
    assert r.status_code == 200 and r.json()["share_token"]
    # เก็บกวาด: ถอนแชร์
    client.delete(f"/gallery/{r.json()['share_token']}", headers={"X-API-Key": "adm-key"})


def test_share_election_403_via_api(client, store):
    r = client.post("/gallery/share", json={"subject": "แคมเปญหาเสียงเลือกตั้ง", "agents": 20})
    assert r.status_code == 403


def test_public_read_and_vote_cycle(client, store):
    r = client.post("/gallery/share", json={"subject": "หัวข้อ public cycle", "agents": 20})
    assert r.status_code == 200
    token = r.json()["share_token"]

    # อ่านสาธารณะ — ไม่ต้องมี key; watermark labels ยังบังคับเสมอ (GOV-03)
    lst = client.get("/gallery.json").json()
    mine = next(i for i in lst["items"] if i["share_token"] == token)
    assert mine["watermark"]["labels"] == [
        "simulation_estimate",
        "not_field_poll",
        "aggregate_only",
    ]

    detail = client.get(f"/gallery/{token}.json").json()
    assert detail["payload"]["tipping_points"] is not None  # snapshot มี key บังคับครบ

    v = client.post(f"/gallery/{token}/vote", json={"vote": "agree"})
    assert v.status_code == 200 and v.json()["votes"]["agree"] >= 1
    assert client.post(f"/gallery/{token}/vote", json={"vote": "maybe"}).status_code == 422

    client.delete(f"/gallery/{token}")
    assert client.get(f"/gallery/{token}.json").status_code == 404
