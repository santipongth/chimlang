"""tests P6-M1..M4: debate engine (mock LLM), runstore, POST /runs, sources, settings"""

import json
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.runstore import RunStore, new_run_id
from simulation.debate import (
    DebatePost,
    DebateUnavailableError,
    _compute_metrics,
    _failure_reason,
    _parse_post,
    run_debate,
)
from simulation.engines import ENGINES, get_engine
from simulation.persona import PersonaFactory
from simulation.sources import ingest_sources, retrieve_context, retrieve_evidence

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม (docker compose up -d)")


@pytest.fixture()
def client() -> TestClient:
    """Keep API tests from changing the developer's persistent UI settings."""
    snapshot = None
    if _pg_ok():
        import psycopg

        from core.appsettings import get_app_settings

        get_app_settings(DSN)
        with psycopg.connect(DSN) as conn:
            row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
            snapshot = row[0] if row else {}
    try:
        yield TestClient(app)
    finally:
        if snapshot is not None:
            import psycopg

            with psycopg.connect(DSN) as conn:
                conn.execute(
                    "UPDATE app_settings SET data = %s WHERE id = 1",
                    (json.dumps(snapshot, ensure_ascii=False),),
                )


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
    assert a.protocol["claim_decomposition"]["main_claim"]
    assert len(a.protocol["per_round_disagreement"]) == 2


def test_debate_failed_posts_flagged_and_excluded():
    # call ที่ 2 และ 5 พัง → ติดธง failed, confidence ถูกลดตามสัดส่วน
    adapter = _FakeAdapter(fail_on={2, 5})
    r = run_debate(_personas(), subject="ทดสอบ", rounds=1, seed=3, adapter=adapter)
    assert r.failed_posts == 2
    assert all(p.content == "" for p in r.posts if p.failed)
    assert r.protocol["failure_taxonomy"]["json_parse_error"] == 2
    assert r.synthesis["confidence"] == pytest.approx(0.8 * (1 - 2 / 6), abs=0.01)


@pytest.mark.parametrize(
    "response",
    [
        'คำตอบตามรูปแบบ:\n{"content":"ทดสอบ","stance":-0.25,"sentiment":0.1}',
        '```json\n{"content":"ทดสอบ","stance":-0.25,"sentiment":0.1}\n```',
    ],
)
def test_debate_parser_accepts_valid_json_wrapped_by_provider(response):
    content, stance, sentiment, want = _parse_post(response)
    assert (content, stance, sentiment, want) == ("ทดสอบ", -0.25, 0.1, "")


def test_debate_parser_still_rejects_malformed_json():
    with pytest.raises(json.JSONDecodeError):
        _parse_post('{"content":"ทดสอบ","stance":0.2,}')


def test_debate_fails_closed_when_every_agent_call_fails():
    adapter = _FakeAdapter(fail_on=set(range(1, 7)))

    with pytest.raises(DebateUnavailableError, match="agent LLM ล้มเหลวทุกคำตอบ"):
        run_debate(_personas(), subject="ทดสอบ", rounds=1, seed=3, adapter=adapter)


def test_debate_marks_analyst_failure_without_mechanical_fallback():
    adapter = _FakeAdapter(fail_on={7})
    result = run_debate(_personas(), subject="ทดสอบ", rounds=1, seed=3, adapter=adapter)

    assert result.metrics["posts_ok"] == 6
    assert result.synthesis["status"] == "analyst_failed"
    assert result.synthesis["fallback"] is False
    assert result.synthesis["summary"] == ""
    assert "mechanical_fallback" not in result.synthesis["parser_mode"]


def test_debate_classifies_llm_transport_failures():
    expected = {
        "APIConnectionError": "llm_connection_error",
        "APITimeoutError": "llm_timeout",
        "RateLimitError": "llm_rate_limit",
        "AuthenticationError": "llm_auth_error",
    }

    for exception_name, reason in expected.items():
        exception_type = type(exception_name, (Exception,), {})
        assert _failure_reason(exception_type()) == reason


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


@needs_pg
def test_source_pii_is_redacted_before_cache_chunks_and_snapshot(monkeypatch):
    import psycopg

    import simulation.sources as src

    url = f"https://cache-pii.example/{uuid4()}"
    result_run_id = new_run_id("debate")
    monkeypatch.setattr(src, "_fetch_text", lambda *args: "ติดต่อ 081-234-5678")
    result = ingest_sources(
        DSN,
        result_run_id,
        [{"kind": "url", "label": "PII cache guard", "url": url}],
    )
    assert result[0]["status"] == "redacted"
    assert result[0]["pii_redactions"] == {"phone": 1}

    cache_key = src.hashlib.sha256(f"url:{url}".encode()).hexdigest()
    with psycopg.connect(DSN) as conn:
        cached = conn.execute(
            "SELECT content, pii_redactions FROM external_fetch_cache WHERE url_hash = %s",
            (cache_key,),
        ).fetchone()
        chunks = conn.execute(
            "SELECT content FROM run_chunks WHERE run_id = %s ORDER BY seq",
            (result_run_id,),
        ).fetchall()
    assert cached and cached[1] == {"phone": 1}
    assert "[PHONE_REDACTED]" in cached[0] and "081-234-5678" not in cached[0]
    assert chunks and all("081-234-5678" not in row[0] for row in chunks)


@needs_pg
def test_source_url_containing_pii_remains_blocked(monkeypatch):
    import simulation.sources as src

    monkeypatch.setattr(
        src,
        "_fetch_text",
        lambda *args: (_ for _ in ()).throw(AssertionError("PII URL must not be fetched")),
    )
    result = ingest_sources(
        DSN,
        new_run_id("debate"),
        [
            {
                "kind": "url",
                "label": "PII URL",
                "url": "https://example.com/?owner=somchai@example.com",
            }
        ],
    )
    assert result[0]["status"] == "blocked"


@needs_pg
def test_source_label_with_pii_is_not_persisted():
    import psycopg

    run_id = new_run_id("debate")
    result = ingest_sources(
        DSN,
        run_id,
        [{"kind": "text", "label": "โทร 081-234-5678", "text": "เนื้อหาปกติ"}],
    )
    assert result[0]["status"] == "blocked"
    assert result[0]["label"] == "text-source"
    with psycopg.connect(DSN) as conn:
        row = conn.execute(
            "SELECT label, error FROM run_sources WHERE run_id = %s ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
    assert "081-234-5678" not in "\n".join(row)


def test_sources_detector_disabled_fails_closed(monkeypatch):
    import simulation.sources as src
    from core.config import Settings

    monkeypatch.setattr(
        src, "get_settings", lambda **kw: Settings(pii_detector_enabled=False, _env_file=None)
    )
    with pytest.raises(ValueError, match="fail-closed"):
        ingest_sources(DSN, "x", [{"kind": "text", "label": "a", "text": "b"}])


def test_source_url_guard_blocks_internal_targets():
    from simulation.sources import validate_external_url

    for url in ("http://localhost:8000/x", "http://127.0.0.1/a", "http://10.0.0.1/a"):
        with pytest.raises(ValueError):
            validate_external_url(url)
    assert validate_external_url("https://example.com/feed") == "https://example.com/feed"


@needs_pg
def test_sources_rich_retrieval_duplicate_and_vector_fallback():
    run_id = new_run_id("debate")
    text = "congestion charge public transport household impact " * 80
    results = ingest_sources(
        DSN,
        run_id,
        [
            {"kind": "text", "label": "source-a", "text": text},
            {"kind": "text", "label": "source-b", "text": text},
        ],
    )
    assert results[0]["quality_score"] > 0
    assert results[1]["status"] == "duplicate"
    assert results[1]["duplicate_of"] == "source-a"
    rich = retrieve_evidence(DSN, run_id, "congestion household", mode="vector")
    assert rich
    assert rich[0]["citation_spans"]
    assert rich[0]["requested_mode"] == "vector"
    assert rich[0]["note"] == "vector_unavailable_fell_back"


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
def test_runstore_lineage_events():
    store = RunStore(DSN)
    store.setup()
    parent = new_run_id("fabric") + "-parent"
    child = new_run_id("fabric") + "-child"
    store.create(
        run_id=parent,
        engine="fabric",
        subject="parent run",
        domain="general",
        agents=20,
        rounds=20,
        seed=1,
        config={},
    )
    store.create(
        run_id=child,
        engine="fabric",
        subject="child run",
        domain="general",
        agents=20,
        rounds=20,
        seed=1,
        config={},
        parent_run_id=parent,
    )
    store.add_event(parent, "retry_requested", actor="test", payload={"child_run_id": child})
    try:
        detail = store.get(child)
        parent_detail = store.get(parent)
        assert detail["parent_run_id"] == parent
        assert any(e["event_type"] == "retry_requested" for e in parent_detail["events"])
    finally:
        store.delete(child)
        store.delete(parent)


@needs_pg
def test_post_runs_fabric_full_governance(client):
    r = client.post(
        "/runs",
        json={
            "engine": "fabric",
            "subject": "ทดสอบ run ถาวร",
            "agents": 20,
            "population_acknowledged": True,
        },
    )
    assert r.status_code == 200
    rid = r.json()["run_id"]
    detail = client.get(f"/runs/{rid}.json").json()
    assert detail["status"] == "complete"
    assert "tipping_points" in detail["payload"]  # PRD ขั้น 7 ติดมากับ payload fabric
    # Run ที่ไม่มี real-world contract ต้องเป็น SimulationFinding และไม่เข้า Calibration
    import psycopg

    with psycopg.connect(DSN) as conn:
        predictions = conn.execute(
            "SELECT count(*) FROM prediction_registry WHERE run_id = %s", (rid,)
        ).fetchone()[0]
        findings = conn.execute(
            "SELECT count(*) FROM simulation_findings WHERE run_id = %s", (rid,)
        ).fetchone()[0]
    assert predictions == 0 and findings == 1
    assert detail["result_kind"] == "simulation_finding"
    assert client.delete(f"/runs/{rid}").status_code == 200
    assert client.get(f"/runs/{rid}.json").status_code == 404


@needs_pg
def test_post_runs_debate_uses_mocked_engine(client, monkeypatch):
    import api.app as app_mod  # noqa: F401
    import simulation.debate as dbt

    monkeypatch.setattr(dbt, "make_debate_adapter", lambda a, r, **kwargs: _FakeAdapter())
    r = client.post(
        "/runs",
        json={
            "engine": "debate",
            "subject": "ทดสอบดีเบตผ่าน api",
            "agents": 6,
            "rounds": 2,
            "population_acknowledged": True,
            "retrieval_mode": "bm25",
        },
    )
    assert r.status_code == 200
    detail = client.get(f"/runs/{r.json()['run_id']}.json").json()
    assert detail["engine"] == "debate" and len(detail["posts"]) == 12
    assert detail["payload"]["synthesis"]["summary"]
    client.delete(f"/runs/{detail['run_id']}")


@needs_pg
def test_post_runs_debate_marks_run_error_when_analyst_fails(client, monkeypatch):
    import simulation.debate as dbt

    subject = f"ทดสอบ analyst fail {uuid4().hex}"
    monkeypatch.setattr(
        dbt,
        "make_debate_adapter",
        lambda a, r, **kwargs: _FakeAdapter(fail_on={7}),
    )
    response = client.post(
        "/runs",
        json={
            "engine": "debate",
            "subject": subject,
            "agents": 6,
            "rounds": 1,
            "population_acknowledged": True,
            "retrieval_mode": "bm25",
        },
    )

    assert response.status_code == 502
    run = RunStore(DSN).list_runs(search=subject, limit=1)[0]
    detail = RunStore(DSN).get(run["run_id"])
    assert detail["status"] == "error"
    assert len(detail["posts"]) == 6
    assert "mechanical fallback" in detail["error"]
    client.delete(f"/runs/{run['run_id']}")


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


def test_api_rejects_too_few_agents_before_db(client):
    assert (
        client.post("/runs", json={"engine": "fabric", "subject": "ทดสอบ", "agents": 0}).status_code
        == 422
    )
    assert (
        client.post("/gallery/share", json={"subject": "หัวข้อแชร์", "agents": -1}).status_code == 422
    )
    assert (
        client.post(
            "/watchlists",
            json={"label": "x", "subject": "หัวข้อ watchlist", "agents": 0, "cadence": "daily"},
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


@needs_pg
def test_post_runs_user_claim_registered(client):
    # เหตุการณ์จริง: claim/measurement/due_days ที่ผู้ใช้ตั้งต้องเข้า registry ตรงตัว
    from datetime import date, timedelta

    r = client.post(
        "/runs",
        json={
            "engine": "fabric",
            "subject": "ทดสอบเหตุการณ์จริงจาก UI",
            "agents": 20,
            "claim": "โพลสำนัก X หลังแถลงจะต่ำกว่า 50%",
            "measurement": "โพลสำนัก X รอบสิ้นเดือน",
            "due_days": 14,
            "population_acknowledged": True,
        },
    )
    assert r.status_code == 200
    rid = r.json()["run_id"]
    import psycopg

    with psycopg.connect(DSN) as conn:
        row = conn.execute(
            "SELECT claim, measurement, due_date, source_kind FROM prediction_registry "
            "WHERE run_id = %s ORDER BY id DESC LIMIT 1",
            (rid,),
        ).fetchone()
    assert row[0] == "โพลสำนัก X หลังแถลงจะต่ำกว่า 50%"
    assert row[1] == "โพลสำนัก X รอบสิ้นเดือน"
    assert row[2] == date.today() + timedelta(days=14)
    assert row[3] == "user"
    client.delete(f"/runs/{rid}")


# ---- LLM ปรับเองได้ (ADR-0006) ----


@needs_pg
def test_llm_settings_overlay_and_reset(client):
    # ตั้ง provider + model จาก UI → effective settings เปลี่ยน; ล้างค่า → กลับไปใช้ .env
    from core.llm.userconfig import LLM_PROVIDERS, effective_llm_settings

    assert "openrouter" in LLM_PROVIDERS and LLM_PROVIDERS["ollama"]["needs_key"] is False
    r = client.put(
        "/settings.json",
        json={
            "llm_provider": "groq",
            "llm_base_url": "https://api.groq.com/openai/v1",
            "llm_model_crowd": "llama-3.3-70b",
        },
    )
    assert r.status_code == 200
    eff = effective_llm_settings()
    assert eff.llm_base_url == "https://api.groq.com/openai/v1"
    assert eff.llm_model_crowd == "llama-3.3-70b"
    data = client.get("/settings.json").json()
    assert data["llm"]["active_model_crowd"] == "llama-3.3-70b"
    assert "llm_api_key" not in str(data)  # key ห้ามออกไปกับ response
    # ล้างค่า = กลับ .env
    client.put(
        "/settings.json",
        json={
            "llm_provider": "",
            "llm_base_url": "",
            "llm_model_crowd": "",
            "llm_model_analyst": "",
        },
    )
    assert (
        effective_llm_settings().llm_model_crowd
        == client.get("/settings.json").json()["llm"]["env_model_crowd"]
    )


@needs_pg
def test_llm_settings_validation(client):
    assert client.put("/settings.json", json={"llm_provider": "quantum-ai"}).status_code == 422
    assert client.put("/settings.json", json={"llm_base_url": "ftp://x"}).status_code == 422
    assert (
        client.put(
            "/settings.json", json={"llm_prices": {"m": {"input_usd_per_m": -1}}}
        ).status_code
        == 422
    )


@needs_pg
def test_llm_custom_price_merges_and_fail_closed(client):
    # ราคาที่ผู้ใช้กรอก merge เข้า registry; model ที่ไม่มีราคา = รันไม่ได้ (fail-closed เดิม)
    from core.llm.pricing import UnknownModelPricingError
    from core.llm.userconfig import effective_pricing

    client.put(
        "/settings.json",
        json={"llm_prices": {"my/custom-model": {"input_usd_per_m": 0.5, "output_usd_per_m": 1.0}}},
    )
    pricing = effective_pricing()
    assert pricing.cost_usd("my/custom-model", 1_000_000, 0) == pytest.approx(0.5)
    with pytest.raises(UnknownModelPricingError):
        pricing.cost_usd("no/price-model", 1000, 0)
    client.put("/settings.json", json={"llm_prices": {}})


# ---- P6-M5: LLM key เข้ารหัส + ราคา + งบเดือน ----


def test_secretbox_roundtrip_and_mask(monkeypatch):
    from cryptography.fernet import Fernet

    import core.secretbox as sb
    from core.config import Settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(sb, "get_settings", lambda **kw: Settings(secret_key=key, _env_file=None))
    ct = sb.encrypt("sk-or-secret-12345")
    assert ct != "sk-or-secret-12345"  # เข้ารหัสจริง
    assert sb.decrypt(ct) == "sk-or-secret-12345"
    assert sb.mask("sk-or-secret-12345").startswith("sk-or-") and "secret" not in sb.mask(
        "sk-or-secret-12345"
    )


def test_secretbox_fails_without_master_key(monkeypatch):
    import core.secretbox as sb
    from core.config import Settings

    monkeypatch.setattr(sb, "get_settings", lambda **kw: Settings(secret_key="", _env_file=None))
    with pytest.raises(sb.MasterKeyMissingError):
        sb.encrypt("x")
    assert sb.master_key_present() is False


def test_secretbox_wrong_master_key_rejected(monkeypatch):
    from cryptography.fernet import Fernet

    import core.secretbox as sb
    from core.config import Settings

    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(sb, "get_settings", lambda **kw: Settings(secret_key=k1, _env_file=None))
    ct = sb.encrypt("secret")
    monkeypatch.setattr(sb, "get_settings", lambda **kw: Settings(secret_key=k2, _env_file=None))
    with pytest.raises(ValueError):  # master key ผิด = ถอดไม่ได้ ไม่คืนมั่ว
        sb.decrypt(ct)


@needs_pg
def test_llm_key_stored_encrypted_and_masked_via_api(client, monkeypatch):
    from cryptography.fernet import Fernet

    import api.auth as auth_mod
    from core.config import Settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        auth_mod, "get_settings", lambda **kw: Settings(secret_key=key, _env_file=None)
    )
    import core.secretbox as sb

    monkeypatch.setattr(sb, "get_settings", lambda **kw: Settings(secret_key=key, _env_file=None))
    # ตั้ง key ผ่าน endpoint แยก
    r = client.put("/settings/llm-key", json={"api_key": "sk-test-abcdef123456"})
    assert r.status_code == 200
    # GET settings: key ถูกมาสก์ ไม่ส่งเต็ม/ไม่ส่ง ciphertext
    data = client.get("/settings.json").json()
    assert data["llm"]["key_present"] and data["llm"]["key_source"] == "db"
    assert "sk-test-abcdef123456" not in json.dumps(data)
    assert "llm_api_key_enc" not in data
    assert "abcdef" not in data["llm"]["key_masked"]  # ส่วนกลางไม่โผล่
    # ลบ key = กลับไป .env
    client.put("/settings/llm-key", json={"api_key": ""})
    assert client.get("/settings.json").json()["llm"]["key_source"] in ("env", "none")


@needs_pg
def test_protected_key_cannot_be_set_via_plain_put(client):
    assert client.put("/settings.json", json={"llm_api_key_enc": "hack"}).status_code == 422


@needs_pg
def test_monthly_budget_blocks_when_exceeded():
    import psycopg

    from core.llm.budget import (
        MonthlyBudgetExceededError,
        check_monthly_budget,
        record_spend,
        spent_this_month,
    )

    before = spent_this_month(DSN)
    run_id = f"test-budget-{uuid4()}"
    try:
        record_spend(DSN, 3.0, run_id=run_id)
        assert spent_this_month(DSN) == pytest.approx(before + 3.0)
        # cap ต่ำกว่ายอดสะสม → block
        with pytest.raises(MonthlyBudgetExceededError):
            check_monthly_budget(DSN, 0.0, cap=before + 1.0)
        # cap 0 = ปิด (ไม่ block)
        check_monthly_budget(DSN, 999.0, cap=0.0)
    finally:
        with psycopg.connect(DSN) as conn:
            conn.execute("DELETE FROM llm_spend WHERE run_id = %s", (run_id,))


@needs_pg
def test_budget_override_from_settings(client):
    response = client.put(
        "/settings.json",
        json={"run_budget_usd_cap": 2.5, "monthly_budget_usd_cap": 20.0},
    )
    assert response.status_code == 200
    from core.llm.userconfig import effective_llm_settings, effective_monthly_cap

    assert effective_llm_settings().run_budget_usd_cap == 2.5
    assert effective_monthly_cap() == 20.0
    data = response.json()
    assert (
        data["budget"]["run_cap_effective"] == 2.5
        and data["budget"]["monthly_cap_effective"] == 20.0
    )


# ---- P6-M6: persona pool + view toggles ----


@needs_pg
def test_persona_pool_census_and_pack(client):
    # default = สำมะโน (census); ระบุ pack = segments ของ pack
    census = client.get("/personas/pool.json").json()
    assert census["source"] == "census" and len(census["segments"]) >= 2
    assert all("name" in s and "share" in s for s in census["segments"])
    assert abs(sum(s["share"] for s in census["segments"]) - 1.0) < 0.02

    r = client.post(
        "/personas/packs",
        json={"label": "pool ทดสอบ", "segments": _pool_segments(), "prompt": ""},
    )
    pid = r.json()["id"]
    pack = client.get("/personas/pool.json", params={"pack_id": pid}).json()
    assert pack["source"].startswith("pack:") and len(pack["segments"]) == 2
    assert client.get("/personas/pool.json", params={"pack_id": 99999999}).status_code == 404


@needs_pg
def test_run_stores_selected_views(client):
    r = client.post(
        "/runs",
        json={
            "engine": "fabric",
            "subject": "ทดสอบ views",
            "agents": 20,
            "views": ["overview", "canvas"],
            "population_acknowledged": True,
        },
    )
    rid = r.json()["run_id"]
    detail = client.get(f"/runs/{rid}.json").json()
    assert set(detail["config"]["views"]) == {"overview", "canvas"}  # เก็บเฉพาะที่เลือก
    client.delete(f"/runs/{rid}")


@needs_pg
def test_run_views_empty_defaults_to_all(client):
    r = client.post(
        "/runs",
        json={
            "engine": "fabric",
            "subject": "ทดสอบ views ว่าง",
            "agents": 20,
            "population_acknowledged": True,
        },
    )
    rid = r.json()["run_id"]
    views = client.get(f"/runs/{rid}.json").json()["config"]["views"]
    assert set(views) == {"overview", "debate", "canvas", "evidence"}  # ว่าง = ครบ
    client.delete(f"/runs/{rid}")


def _pool_segments():
    return [
        {
            "id": f"pool_{i}",
            "name": f"กลุ่ม pool {i}",
            "share": 0.5,
            "voice_activity": 0.5,
            "cultural_priors": {"kreng_jai": 0.5, "say_do_gap": 0.4, "sarcasm_meme": 0.3},
            "channel_mix": {
                "line_closed_group": 0.3,
                "public_feed": 0.3,
                "algo_feed": 0.25,
                "offline_wom": 0.15,
            },
            "traits": ["ทดสอบ"],
        }
        for i in range(2)
    ]


# ---- Share toggle ต่อ run (P7 — เปิด/ปิดแชร์สู่ gallery แบบ studio) ----


@needs_pg
def test_run_share_toggle_cycle(client):
    r = client.post(
        "/runs",
        json={
            "engine": "fabric",
            "subject": "ทดสอบ share toggle",
            "agents": 20,
            "population_acknowledged": True,
        },
    )
    rid = r.json()["run_id"]
    # ยังไม่แชร์
    assert client.get(f"/runs/{rid}.json").json()["share_token"] is None
    # เปิดแชร์ → snapshot payload จริงของ run (ไม่รันใหม่) + idempotent
    t1 = client.post(f"/runs/{rid}/share").json()["share_token"]
    assert client.post(f"/runs/{rid}/share").json()["share_token"] == t1
    assert client.get(f"/runs/{rid}.json").json()["share_token"] == t1
    g = client.get(f"/gallery/{t1}.json").json()
    assert g["subject"] == "ทดสอบ share toggle"
    assert g["payload"]["engine"] == "fabric"  # payload มาจาก run ที่เก็บไว้
    # ปิดแชร์ → ลิงก์เดิมตาย + สถานะกลับเป็นไม่แชร์
    client.delete(f"/runs/{rid}/share")
    assert client.get(f"/runs/{rid}.json").json()["share_token"] is None
    assert client.get(f"/gallery/{t1}.json").status_code == 404
    # เปิดใหม่ = token ใหม่ (snapshot ใหม่ — ของเดิมถูกถอนถาวร)
    t2 = client.post(f"/runs/{rid}/share").json()["share_token"]
    assert t2 != t1
    client.delete(f"/runs/{rid}/share")
    client.delete(f"/runs/{rid}")


@needs_pg
def test_run_share_blocks_election(client):
    r = client.post(
        "/runs",
        json={
            "engine": "fabric",
            "subject": "ทดสอบ ผลเลือกตั้งผู้ว่าฯ รอบใหม่",
            "agents": 20,
            "population_acknowledged": True,
        },
    )
    rid = r.json()["run_id"]
    assert client.post(f"/runs/{rid}/share").status_code == 403  # election ห้ามแชร์ (ADR-0004)
    client.delete(f"/runs/{rid}")
