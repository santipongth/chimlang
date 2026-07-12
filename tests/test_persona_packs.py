"""tests P5-M7: persona packs — validation + PII gate, store, AI-generate (mock LLM), endpoints"""

import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from api.app import app
from simulation.persona_packs import (
    PackStore,
    PackValidationError,
    PIIInPackError,
    factory_from_pack,
    validate_pack,
)

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _segments(n: int = 2) -> list[dict]:
    share = round(1.0 / n, 4)
    segs = [
        {
            "id": f"seg_{i}",
            "name": f"กลุ่มทดสอบที่ {i + 1}",
            "share": share,
            "voice_activity": 0.5,
            "cultural_priors": {"kreng_jai": 0.5, "say_do_gap": 0.4, "sarcasm_meme": 0.3},
            "channel_mix": {
                "line_closed_group": 0.3,
                "public_feed": 0.3,
                "algo_feed": 0.25,
                "offline_wom": 0.15,
            },
            "traits": ["ห่วงค่าครองชีพ"],
        }
        for i in range(n)
    ]
    segs[0]["share"] = round(1.0 - share * (n - 1), 4)
    return segs


@pytest.fixture(scope="module")
def store() -> PackStore:
    s = PackStore(DSN)
    try:
        s.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    return s


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---- validation + PII gate ----


def test_valid_pack_passes():
    validate_pack("pack ทดสอบ", _segments(3))


def test_share_must_sum_to_one():
    segs = _segments(2)
    segs[0]["share"] = 0.9  # รวมเกิน 1
    with pytest.raises(PackValidationError):
        validate_pack("x", segs)


def test_channel_mix_rejects_unknown_channel():
    segs = _segments(2)
    segs[0]["channel_mix"] = {"twitter": 1.0}
    with pytest.raises(PackValidationError):
        validate_pack("x", segs)


def test_pii_in_pack_blocked():
    segs = _segments(2)
    segs[0]["traits"] = ["ติดต่อคุณสมชายที่ 081-234-5678"]  # เบอร์โทร = PII
    with pytest.raises(PIIInPackError):
        validate_pack("x", segs)


def test_detector_disabled_fails_closed(monkeypatch):
    import simulation.persona_packs as pp
    from core.config import Settings

    monkeypatch.setattr(
        pp, "get_settings", lambda **kw: Settings(pii_detector_enabled=False, _env_file=None)
    )
    with pytest.raises(PackValidationError, match="fail-closed"):
        validate_pack("x", _segments(2))


def test_segment_count_bounds():
    with pytest.raises(PackValidationError):
        validate_pack("x", _segments(1))


# ---- store + factory ----


def test_store_create_get_and_factory_sampling(store):
    pid = store.create(
        label="pack ทดสอบ store", segments=_segments(3), prompt="ทดสอบ", created_by="test"
    )
    pack = store.get(pid)
    assert pack.label == "pack ทดสอบ store" and len(pack.segments) == 3
    # factory จาก pack ต้อง sample ได้จริงและ segment ชื่อตรง
    personas = factory_from_pack(pack).sample(12, seed=1, max_agents=12)
    assert len(personas) == 12
    assert {p.segment_name for p in personas} <= {s["name"] for s in pack.segments}
    store.delete(pid)
    with pytest.raises(ValueError):
        store.get(pid)


# ---- AI generate (mock adapter — ห้ามเรียก LLM จริงใน test) ----


@dataclass
class _FakeResult:
    text: str


class _FakeAdapter:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0

    def chat(self, tier, messages, **kw):
        self.calls += 1
        return _FakeResult(text=self._responses.pop(0))


def test_generate_parses_and_normalizes_share():
    from simulation.persona_ai import generate_pack_from_prompt

    raw = {"segments": _segments(2)}
    raw["segments"][0]["share"] = 0.62  # รวม 0.62+0.5=1.12 → ต้องถูก normalize
    raw["segments"][1]["share"] = 0.5
    adapter = _FakeAdapter([json.dumps(raw, ensure_ascii=False)])
    segs = generate_pack_from_prompt("คนเมือง", label="ทดสอบ", adapter=adapter)
    assert abs(sum(s["share"] for s in segs) - 1.0) < 0.001
    assert adapter.calls == 1


def test_generate_retries_once_on_parse_fail_then_raises():
    from simulation.persona_ai import generate_pack_from_prompt

    adapter = _FakeAdapter(["ไม่ใช่ json", "ก็ยังไม่ใช่ json"])
    with pytest.raises(ValueError, match="retry"):
        generate_pack_from_prompt("คนเมือง", label="ทดสอบ", adapter=adapter)
    assert adapter.calls == 2  # ยิงซ้ำแค่ 1 ครั้งตาม pattern judge


def test_generate_blocks_pii_from_model():
    # ต่อให้ model กุชื่อบุคคลจริงมา — ด่าน validate_pack ต้องจับ
    from simulation.persona_ai import generate_pack_from_prompt

    bad = {"segments": _segments(2)}
    bad["segments"][0]["traits"] = ["แฟนคลับ นายทดสอบ ใจดี โทร 081-234-5678"]
    adapter = _FakeAdapter([json.dumps(bad, ensure_ascii=False)] * 2)
    with pytest.raises(ValueError):
        generate_pack_from_prompt("คนเมือง", label="ทดสอบ", adapter=adapter)


def test_try_ask_sanitizes_think_tag():
    from simulation.persona_ai import try_ask

    adapter = _FakeAdapter(["<think>คิดในใจ</think>ไม่เห็นด้วยค่ะ กลัวกระทบค่าใช้จ่าย"])
    answer = try_ask(_segments(2)[0], "คิดยังไงกับมาตรการนี้", adapter=adapter)
    assert "think" not in answer and answer.startswith("ไม่เห็นด้วย")


# ---- endpoints (mock ชั้น LLM) ----


def test_pack_endpoints_cycle_and_pack_id_in_dashboard(client, store):
    r = client.post(
        "/personas/packs",
        json={"label": "pack ผ่าน api", "segments": _segments(2), "prompt": "ทดสอบ"},
    )
    assert r.status_code == 200
    pid = r.json()["id"]
    packs = client.get("/personas/packs.json").json()["packs"]
    assert any(p["id"] == pid for p in packs)

    # dashboard ใช้ pack นี้ — segment ในผลต้องเป็นชื่อจาก pack ไม่ใช่สำมะโน
    d = client.get(
        "/dashboard.json", params={"subject": "ทดสอบ pack", "agents": 20, "pack_id": pid}
    )
    assert d.status_code == 200
    segs = set(d.json()["scenarios"][0]["belief_by_segment"].keys())
    assert segs <= {"กลุ่มทดสอบที่ 1", "กลุ่มทดสอบที่ 2"}

    assert client.delete(f"/personas/packs/{pid}").status_code == 200
    # pack หาย → dashboard ด้วย pack_id นี้ = 404
    assert (
        client.get(
            "/dashboard.json", params={"subject": "ทดสอบ", "agents": 20, "pack_id": pid}
        ).status_code
        == 404
    )


def test_pack_create_rejects_pii_via_api(client, store):
    segs = _segments(2)
    segs[0]["traits"] = ["อีเมล test@example.com"]
    r = client.post("/personas/packs", json={"label": "x", "segments": segs})
    assert r.status_code == 422


def test_generate_endpoint_uses_mocked_generator(client, monkeypatch):
    import api.app as app_mod  # noqa: F401 — endpoint import ภายใน function
    import simulation.persona_ai as pai

    monkeypatch.setattr(pai, "generate_pack_from_prompt", lambda p, label: _segments(3))
    r = client.post("/personas/packs/generate", json={"label": "gen", "prompt": "คนเมืองรุ่นใหม่"})
    assert r.status_code == 200
    assert len(r.json()["segments"]) == 3


def test_try_ask_endpoint_mocked(client, monkeypatch):
    import simulation.persona_ai as pai

    monkeypatch.setattr(pai, "try_ask", lambda seg, q: "ไม่แน่ใจค่ะ ขอดูรายละเอียดก่อน")
    r = client.post(
        "/personas/try-ask", json={"segment": _segments(2)[0], "question": "คิดยังไงกับเรื่องนี้"}
    )
    assert r.status_code == 200 and "ไม่แน่ใจ" in r.json()["answer"]
