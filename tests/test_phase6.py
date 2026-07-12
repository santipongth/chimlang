"""tests P6-M1..M4: debate engine (mock LLM), runstore, POST /runs, sources, settings"""

import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.runstore import RunStore, new_run_id
from simulation.debate import DebatePost, _compute_metrics, run_debate
from simulation.engines import ENGINES, get_engine
from simulation.persona import PersonaFactory
from simulation.sources import ingest_sources, retrieve_context

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม (docker compose up -d)")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---- engine registry ----


def test_engine_registry_caps():
    assert set(ENGINES) == {"fabric", "debate"}
    assert get_engine("fabric").max_agents == 1000
    assert get_engine("debate").max_agents == 40
    with pytest.raises(ValueError):
        get_engine("mirofish")  # อยู่ในแผนระยะยาว — ยังไม่มี


# ---- debate engine (FakeAdapter — ไม่เรียก LLM จริง) ----


@dataclass
class _R:
    text: str


class _FakeAdapter:
    """ตอบ JSON ตาม stance ที่กำหนดต่อ call — และนับจำนวน call"""

    def __init__(self, stance: float = 0.5, fail_on: set[int] | None = None):
        self.stance = stance
        self.fail_on = fail_on or set()
        self.calls = 0

    def chat(self, tier, messages, **kw):
        self.calls += 1
        if self.calls in self.fail_on:
            return _R("ไม่ใช่ json เลย")
        if "นักวิเคราะห์" in messages[0]["content"]:
            return _R(
                json.dumps(
                    {
                        "summary": "สรุปทดสอบ",
                        "confidence": 0.8,
                        "distribution": [{"bucket": "เห็นด้วย", "pct": 100}],
                        "key_drivers": ["ปัจจัยทดสอบ"],
                        "risks": ["ความเสี่ยงทดสอบ"],
                    },
                    ensure_ascii=False,
                )
            )
        return _R(
            json.dumps(
                {"content": "โพสต์ทดสอบภาษาไทย", "stance": self.stance, "sentiment": 0.1},
                ensure_ascii=False,
            )
        )


def _personas(n=6):
    return PersonaFactory().sample(n, seed=1, max_agents=n)


def test_debate_runs_and_is_seed_deterministic_in_sampling():
    a = run_debate(_personas(), subject="ทดสอบดีเบต", rounds=2, seed=7, adapter=_FakeAdapter())
    b = run_debate(_personas(), subject="ทดสอบดีเบต", rounds=2, seed=7, adapter=_FakeAdapter())
    assert [p.to_dict() for p in a.posts] == [p.to_dict() for p in b.posts]
    assert a.metrics["posts_ok"] == 12 and a.failed_posts == 0
    assert a.synthesis["confidence"] == 0.8 and not a.synthesis["fallback"]


def test_debate_failed_posts_flagged_and_excluded():
    # call ที่ 2 และ 5 พัง → ติดธง failed, confidence ถูกลดตามสัดส่วน
    adapter = _FakeAdapter(fail_on={2, 5})
    r = run_debate(_personas(), subject="ทดสอบ", rounds=1, seed=3, adapter=adapter)
    assert r.failed_posts == 2
    assert all(p.content == "" for p in r.posts if p.failed)
    assert r.synthesis["confidence"] == pytest.approx(0.8 * (1 - 2 / 6), abs=0.01)


def test_debate_cap_enforced():
    with pytest.raises(ValueError, match="40"):
        run_debate(
            PersonaFactory().sample(41, seed=1, max_agents=50),
            subject="x",
            rounds=1,
            seed=1,
            adapter=_FakeAdapter(),
        )


def test_debate_redteam_initial_stance():
    from simulation.debate import _initial_stance
    from simulation.redteam_population import RED_TEAM

    assert _initial_stance(RED_TEAM[0]) == -0.6  # contrarian
    assert _initial_stance(RED_TEAM[1]) == -0.3  # auditor
    assert _initial_stance(_personas(4)[0]) == 0.0


def test_debate_metrics_tipping_on_stance_jump():
    posts = [DebatePost(0, i, "s", "x", -0.5, 0.0) for i in range(4)] + [
        DebatePost(1, i, "s", "x", 0.5, 0.0) for i in range(4)
    ]
    m = _compute_metrics(posts, rounds=2, agent_count=4)
    assert m["tipping_points"], "stance กระโดด 1.0 ต้องเป็น tipping"


# ---- sources (M3) ----


@needs_pg
def test_sources_pii_blocked_and_lexical_retrieval():
    run_id = new_run_id("debate")
    results = ingest_sources(
        DSN,
        run_id,
        [
            {"kind": "text", "label": "ปกติ", "text": "นโยบายค่าธรรมเนียมรถติดในเขตเมือง " * 30},
            {"kind": "text", "label": "มี PII", "text": "ติดต่อคุณทดสอบ โทร 081-234-5678"},
        ],
    )
    by_label = {r["label"]: r for r in results}
    assert by_label["ปกติ"]["status"] == "ready" and by_label["ปกติ"]["chunks"] >= 1
    assert by_label["มี PII"]["status"] == "blocked"  # ทั้งชิ้นถูก block (GOV-01)
    ctx = retrieve_context(DSN, run_id, "ค่าธรรมเนียมรถติด", k=3)
    assert ctx and "ค่าธรรมเนียมรถติด" in ctx[0]
    assert retrieve_context(DSN, "ไม่มี-run-นี้", "x") == ()


def test_sources_detector_disabled_fails_closed(monkeypatch):
    import simulation.sources as src
    from core.config import Settings

    monkeypatch.setattr(
        src, "get_settings", lambda **kw: Settings(pii_detector_enabled=False, _env_file=None)
    )
    with pytest.raises(ValueError, match="fail-closed"):
        ingest_sources(DSN, "x", [{"kind": "text", "label": "a", "text": "b"}])


# ---- runstore + POST /runs (M2) ----


@needs_pg
def test_runstore_crud():
    store = RunStore(DSN)
    store.setup()
    rid = new_run_id("fabric")
    store.create(
        run_id=rid,
        engine="fabric",
        subject="ทดสอบ store",
        domain="ทั่วไป",
        agents=20,
        rounds=20,
        seed=42,
        config={},
    )
    store.add_posts(
        rid,
        [
            {
                "round_no": 0,
                "agent_idx": 0,
                "segment": "s",
                "content": "x",
                "stance": 0.1,
                "sentiment": 0.0,
            }
        ],
    )
    store.finish(rid, {"ok": True})
    got = store.get(rid)
    assert got["status"] == "complete" and got["payload"] == {"ok": True} and len(got["posts"]) == 1
    assert any(r["run_id"] == rid for r in store.list_runs(search="ทดสอบ store"))
    store.delete(rid)
    with pytest.raises(ValueError):
        store.get(rid)


@needs_pg
def test_post_runs_fabric_full_governance(client):
    r = client.post("/runs", json={"engine": "fabric", "subject": "ทดสอบ run ถาวร", "agents": 20})
    assert r.status_code == 200
    rid = r.json()["run_id"]
    detail = client.get(f"/runs/{rid}.json").json()
    assert detail["status"] == "complete"
    assert "tipping_points" in detail["payload"]  # PRD ขั้น 7 ติดมากับ payload fabric
    # ทุก run ต้องมี prediction ≥1 (กฎเหล็กข้อ 3)
    import psycopg

    with psycopg.connect(DSN) as conn:
        n = conn.execute(
            "SELECT count(*) FROM prediction_registry WHERE run_id = %s", (rid,)
        ).fetchone()[0]
    assert n >= 1
    assert client.delete(f"/runs/{rid}").status_code == 200
    assert client.get(f"/runs/{rid}.json").status_code == 404


@needs_pg
def test_post_runs_debate_uses_mocked_engine(client, monkeypatch):
    import api.app as app_mod  # noqa: F401
    import simulation.debate as dbt

    monkeypatch.setattr(dbt, "make_debate_adapter", lambda a, r: _FakeAdapter())
    r = client.post(
        "/runs",
        json={"engine": "debate", "subject": "ทดสอบดีเบตผ่าน api", "agents": 6, "rounds": 2},
    )
    assert r.status_code == 200
    detail = client.get(f"/runs/{r.json()['run_id']}.json").json()
    assert detail["engine"] == "debate" and len(detail["posts"]) == 12
    assert detail["payload"]["synthesis"]["summary"]
    client.delete(f"/runs/{detail['run_id']}")


@needs_pg
def test_post_runs_guards(client):
    # PII ในหัวข้อ = 422 | engine ไม่รู้จัก = 422 | sources กับ fabric = 422
    assert (
        client.post("/runs", json={"engine": "fabric", "subject": "โทรหา 081-234-5678"}).status_code
        == 422
    )
    assert client.post("/runs", json={"engine": "mirofish", "subject": "ทดสอบ"}).status_code == 422
    assert (
        client.post(
            "/runs",
            json={
                "engine": "fabric",
                "subject": "ทดสอบ sources",
                "sources": [{"kind": "text", "label": "x", "text": "y"}],
            },
        ).status_code
        == 422
    )


# ---- settings (M4) ----


@needs_pg
def test_settings_get_put_cycle(client):
    data = client.get("/settings.json").json()
    assert data["default_engine"] in ("fabric", "debate") and "caps" in data
    r = client.put("/settings.json", json={"default_engine": "debate", "default_agents": 20})
    assert r.status_code == 200 and r.json()["default_engine"] == "debate"
    assert client.get("/settings.json").json()["default_agents"] == 20
    assert client.put("/settings.json", json={"default_engine": "quantum"}).status_code == 422
    assert client.put("/settings.json", json={"unknown_key": 1}).status_code == 422
    client.put("/settings.json", json={"default_engine": "fabric", "default_agents": 100})
