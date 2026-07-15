"""P7 News Desk — governance (hindcast/PII) + reproducibility + media diet"""

import os
from datetime import date
from uuid import uuid4

import pytest

from core.run_context import ExternalRetrievalBlockedError, RunContext
from simulation.newsdesk import NewsItem, dedupe_intents, gather, load_items, segment_feed

DSN = os.environ.get("CHIMLANG_TEST_DSN", "postgresql://chimlang:chimlang@localhost:5432/chimlang")


def _pg_up() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_up(), reason="ต้องมี PostgreSQL (docker compose up -d)")


def _item(provider: str, title: str, content: str, status: str = "ready") -> NewsItem:
    from simulation.newsdesk import CHANNEL_TAGS

    return NewsItem(provider, "", title, content, "2026-07-12", CHANNEL_TAGS[provider], status)


# ---- กฎเหล็กข้อ 2: hindcast = block ตายก่อนแตะเน็ต ----


@needs_pg
def test_gather_blocked_in_hindcast_mode():
    ctx = RunContext(
        run_id="news-leak-test", seed=1, hindcast_mode=True, cutoff_date=date(2024, 1, 1)
    )
    with pytest.raises(ExternalRetrievalBlockedError):
        gather(DSN, ctx, feeds=["https://example.com/feed"], queries=["อะไรก็ตาม"])


@needs_pg
def test_gather_fail_closed_when_pii_detector_off(monkeypatch):
    import simulation.newsdesk as nd
    from core.config import Settings

    monkeypatch.setattr(
        nd, "get_settings", lambda **kw: Settings(pii_detector_enabled=False, _env_file=None)
    )
    ctx = RunContext(run_id="news-pii-off", seed=1)
    with pytest.raises(ValueError, match="GOV-01"):
        gather(DSN, ctx, feeds=[], queries=[])


@needs_pg
def test_gather_redacts_pii_before_cache_and_snapshot(monkeypatch):
    """PII ใน body ถูก redact ก่อน cache/snapshot และชิ้นข่าวยังใช้งานได้"""
    import simulation.newsdesk as nd

    monkeypatch.setattr(
        nd,
        "_fetch_rss_items",
        lambda url: [
            ("ข่าวปกติ", "ข่าวปกติ\nคณะกรรมการแถลงมาตรการใหม่วันนี้"),
            ("ข่าวมี PII", "ข่าวมี PII\nติดต่อคุณสมชายที่เบอร์ 081-234-5678 ด่วน"),
        ],
    )
    feed = f"https://mock.feed/{uuid4()}.rss"
    ctx = RunContext(run_id="news-pii-item", seed=1)
    items = gather(DSN, ctx, feeds=[feed], queries=[])
    ready = [it for it in items if it.status == "ready"]
    redacted = [it for it in items if it.status == "redacted"]
    assert len(ready) == 1 and len(redacted) == 1
    assert "[PHONE_REDACTED]" in redacted[0].content
    assert redacted[0].pii_redactions == {"phone": 1}
    assert "081-234-5678" not in redacted[0].content

    stored = [it for it in load_items(DSN, "news-pii-item") if it.status == "redacted"]
    assert stored and stored[-1].pii_redactions == {"phone": 1}
    import psycopg

    with psycopg.connect(DSN) as conn:
        cached = conn.execute(
            "SELECT payload::text FROM news_fetch_cache WHERE cache_key = %s",
            (nd._cache_key("rss", feed, feed),),
        ).fetchone()
    assert cached and "[PHONE_REDACTED]" in cached[0]
    assert "081-234-5678" not in cached[0]


@needs_pg
def test_gather_snapshots_provider_failures(monkeypatch):
    """provider ล้ม/ไม่มี key ต้องมี snapshot ใน evidence ไม่หายเงียบ"""
    import simulation.newsdesk as nd
    from core.config import Settings

    def _rss_fail(url):
        raise RuntimeError("feed down")

    monkeypatch.setattr(nd, "_fetch_rss_items", _rss_fail)
    monkeypatch.setattr(
        nd,
        "get_settings",
        lambda **kw: Settings(news_rss_feeds="", tavily_api_key="", _env_file=None),
    )
    monkeypatch.setattr(nd, "effective_news_config", lambda settings: ([], ""))
    ctx = RunContext(run_id="news-provider-fail", seed=1)
    items = gather(DSN, ctx, feeds=["https://example.com/rss"], queries=["ทดสอบค้นข่าว"])
    statuses = {it.provider: it.status for it in items}
    assert statuses["rss"] == "error"
    assert statuses["search"] == "skipped"
    stored = load_items(DSN, "news-provider-fail")
    assert any(it.provider == "rss" and "feed down" in it.error for it in stored)
    assert any(it.provider == "search" and "TAVILY_API_KEY" in it.error for it in stored)


@needs_pg
def test_gather_reuses_successful_provider_cache(monkeypatch):
    import simulation.newsdesk as nd

    calls = {"rss": 0}
    feed = f"https://cache.feed/{uuid4()}.rss"

    def _rss(url):
        calls["rss"] += 1
        return [("ข่าว cache", "ข่าว cache\nเนื้อหาข่าวทั่วไป")]

    monkeypatch.setattr(nd, "_fetch_rss_items", _rss)
    first = gather(
        DSN, RunContext(run_id=f"news-cache-a-{uuid4()}", seed=1), feeds=[feed], queries=[]
    )
    second = gather(
        DSN, RunContext(run_id=f"news-cache-b-{uuid4()}", seed=1), feeds=[feed], queries=[]
    )
    assert calls["rss"] == 1
    assert [x.status for x in first] == ["ready"]
    assert [x.status for x in second] == ["ready"]


# ---- NFR-07: replay จาก snapshot ไม่แตะเน็ต + deterministic ----


@needs_pg
def test_load_items_reads_snapshot_only(monkeypatch):
    """replay ต้องไม่ยิงเน็ต — mock httpx ให้ระเบิดถ้าถูกเรียก"""
    import httpx

    def _boom(*a, **kw):
        raise AssertionError("replay ห้ามแตะเน็ต (NFR-07)")

    monkeypatch.setattr(httpx, "get", _boom)
    monkeypatch.setattr(httpx, "post", _boom)
    items = load_items(DSN, "news-pii-item")  # จาก test ก่อนหน้า
    assert len(items) >= 1


def test_segment_feed_deterministic_and_diet_differs():
    items = [
        _item("rss", f"ข่าวสาธารณะ {i}", f"เนื้อหาข่าวสาธารณะเรื่องนโยบายรถไฟฟ้า {i}") for i in range(6)
    ] + [_item("search", f"ผลค้น {i}", f"กระแสในโซเชียลเรื่องนโยบายรถไฟฟ้า {i}") for i in range(6)]
    mix_line = {
        "line_closed_group": 0.7,
        "public_feed": 0.2,
        "algo_feed": 0.05,
        "offline_wom": 0.05,
    }
    mix_algo = {"algo_feed": 0.7, "public_feed": 0.1, "line_closed_group": 0.1, "offline_wom": 0.1}
    subject = "นโยบายรถไฟฟ้า"
    a1 = segment_feed(items, mix_line, subject, k=4, seed=42)
    a2 = segment_feed(items, mix_line, subject, k=4, seed=42)
    b = segment_feed(items, mix_algo, subject, k=4, seed=42)
    assert [x.title for x in a1] == [x.title for x in a2]  # seed เดิม = feed เดิมเป๊ะ
    assert [x.title for x in a1] != [x.title for x in b]  # diet ต่าง = เห็นข่าวต่าง
    # กลุ่ม algo หนักต้องได้ข่าวจาก search (algo_feed สูง) นำ
    assert b[0].provider == "search" and a1[0].provider == "rss"


def test_segment_feed_excludes_blocked():
    items = [
        _item("rss", "ปกติ", "เนื้อหาปกติเรื่องนโยบาย"),
        _item("rss", "โดน block", "", status="blocked"),
    ]
    mix = {"public_feed": 1.0}
    out = segment_feed(items, mix, "นโยบาย", k=5, seed=1)
    assert [x.title for x in out] == ["ปกติ"]


def test_segment_feed_includes_redacted_items():
    items = [_item("rss", "ผ่านการลบ PII", "ติดต่อ [PHONE_REDACTED]", status="redacted")]
    out = segment_feed(items, {"public_feed": 1.0}, "ติดต่อ", k=5, seed=1)
    assert out == items


def test_news_url_containing_pii_is_blocked_without_persistable_raw_value():
    import json

    import simulation.newsdesk as nd
    from governance.pii import PIIDetector

    raw_url = "https://example.com/?owner=somchai@example.com"
    prepared = nd._prepare_news_payload(
        "search",
        [("ข่าว", raw_url, "เนื้อหาที่ไม่พบข้อมูลส่วนบุคคล")],
        PIIDetector(),
    )
    assert prepared[0]["status"] == "blocked"
    assert prepared[0]["url"] == ""
    assert "somchai@example.com" not in json.dumps(prepared, ensure_ascii=False)


@needs_pg
def test_news_query_with_pii_is_not_persisted(monkeypatch):
    import json

    import simulation.newsdesk as nd

    monkeypatch.setattr(nd, "effective_news_config", lambda settings: ([], "test-key"))
    monkeypatch.setattr(
        nd,
        "_tavily_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("PII query must not reach provider")
        ),
    )
    run_id = f"news-query-pii-{uuid4()}"
    items = gather(
        DSN,
        RunContext(run_id=run_id, seed=1),
        feeds=[],
        queries=["ติดต่อ somchai@example.com"],
    )
    serialized = json.dumps([item.__dict__ for item in items], ensure_ascii=False)
    assert items and items[0].status == "blocked"
    assert "somchai@example.com" not in serialized
    assert "somchai@example.com" not in json.dumps(
        [item.__dict__ for item in load_items(DSN, run_id)], ensure_ascii=False
    )


@needs_pg
def test_legacy_pii_error_metadata_migration_scrubs_values():
    import psycopg

    from scripts.db_migrations import _scrub_legacy_pii_error_metadata
    from simulation.newsdesk import setup_newsdesk
    from simulation.sources import setup_sources

    setup_newsdesk(DSN)
    setup_sources(DSN)
    run_id = f"legacy-pii-{uuid4()}"
    with psycopg.connect(DSN) as conn:
        news_id = conn.execute(
            "INSERT INTO news_items "
            "(run_id, provider, content_hash, status, error) "
            "VALUES (%s, 'rss', %s, 'blocked', %s) RETURNING id",
            (run_id, run_id, "พบ phone: 081-234-5678"),
        ).fetchone()[0]
        source_id = conn.execute(
            "INSERT INTO run_sources (run_id, kind, label, status, error) "
            "VALUES (%s, 'text', 'legacy', 'blocked', %s) RETURNING id",
            (run_id, "พบ email: somchai@example.com"),
        ).fetchone()[0]
    try:
        _scrub_legacy_pii_error_metadata(DSN)
        with psycopg.connect(DSN) as conn:
            news_error = conn.execute(
                "SELECT error FROM news_items WHERE id = %s", (news_id,)
            ).fetchone()[0]
            source_error = conn.execute(
                "SELECT error FROM run_sources WHERE id = %s", (source_id,)
            ).fetchone()[0]
        assert "081-234-5678" not in news_error
        assert "somchai@example.com" not in source_error
    finally:
        with psycopg.connect(DSN) as conn:
            conn.execute("DELETE FROM news_items WHERE id = %s", (news_id,))
            conn.execute("DELETE FROM run_sources WHERE id = %s", (source_id,))


def test_dedupe_intents_caps_and_merges():
    intents = [
        "ราคาค่าโดยสารรถไฟฟ้าสายสีเขียว",
        "ราคาค่าโดยสารรถไฟฟ้าสายสีเขียวล่าสุด",  # ใกล้เคียง → ถูกรวบ
        "ผลกระทบต่อคนรายได้น้อย",
        "สถิติผู้โดยสารต่อวัน",
        "ความเห็นผู้ว่าฯ",  # เกิน cap 3 → ตัด
    ]
    out = dedupe_intents(intents, cap=3)
    assert len(out) == 3 and out[0] == "ราคาค่าโดยสารรถไฟฟ้าสายสีเขียว"
    assert "ผลกระทบต่อคนรายได้น้อย" in out


def test_debate_prompts_include_segment_news(monkeypatch):
    """agent ต้องเห็นข่าวของกลุ่มตัวเอง และ intent ถูกส่งให้ fetcher ระหว่างรอบ"""
    import json as _json

    from simulation.debate import run_debate
    from simulation.persona import PersonaFactory

    personas = PersonaFactory().sample(4, seed=7, max_agents=4)
    seg = personas[0].segment_name
    seen_prompts: list[str] = []
    fetch_calls: list[list[str]] = []

    class _FakeResult:
        def __init__(self):
            self.text = _json.dumps(
                {
                    "content": "ขอดูข้อมูลก่อนนะ",
                    "stance": 0.1,
                    "sentiment": 0.0,
                    "want_to_know": "ราคาล่าสุด",
                },
                ensure_ascii=False,
            )

    class _FakeAdapter:
        def chat(self, tier, messages, **kw):
            seen_prompts.append(messages[1]["content"])
            return _FakeResult()

    def fetcher(queries):
        fetch_calls.append(queries)
        return {seg: ("ข่าวใหม่จาก intent",)}

    result = run_debate(
        personas,
        subject="ทดสอบข่าว",
        rounds=2,
        seed=7,
        adapter=_FakeAdapter(),
        segment_news={seg: ("ข่าวเฉพาะกลุ่มนี้",)},
        news_fetcher=fetcher,
    )
    seg_prompts = [p for p in seen_prompts if "ข่าวเฉพาะกลุ่มนี้" in p]
    other_prompts = [p for p in seen_prompts if "ข่าวเฉพาะกลุ่มนี้" not in p]
    assert seg_prompts and other_prompts  # เห็นเฉพาะกลุ่มที่มีข่าว = media diet จริง
    assert fetch_calls and fetch_calls[0] == ["ราคาล่าสุด"]  # intent ถูกรวบส่งโต๊ะข่าว
    # ข่าวจาก intent เข้ารอบถัดไปของกลุ่มนั้น
    assert any("ข่าวใหม่จาก intent" in p for p in seen_prompts)
    assert result.metrics["posts_ok"] == 8


# ---- ตั้ง feeds/Tavily key จากหน้า Settings (DB ทับ .env) ----


@needs_pg
def test_effective_news_config_db_overrides_env(monkeypatch):
    from cryptography.fernet import Fernet

    import core.secretbox as sb
    from core.appsettings import put_app_settings, set_tavily_api_key
    from core.config import Settings
    from simulation.newsdesk import effective_news_config

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(sb, "get_settings", lambda **kw: Settings(secret_key=key, _env_file=None))
    env_settings = Settings(
        news_rss_feeds="https://env.feed/rss", tavily_api_key="env-key", _env_file=None
    )
    # ยังไม่ตั้งใน DB → ใช้ .env
    put_app_settings(DSN, {"news_rss_feeds": ""})
    set_tavily_api_key(DSN, "")
    feeds, tk = effective_news_config(env_settings)
    assert feeds == ["https://env.feed/rss"] and tk == "env-key"
    # ตั้งใน DB → ทับ .env
    put_app_settings(DSN, {"news_rss_feeds": "https://db.feed/a, https://db.feed/b"})
    set_tavily_api_key(DSN, "db-tavily-key")
    feeds, tk = effective_news_config(env_settings)
    assert feeds == ["https://db.feed/a", "https://db.feed/b"] and tk == "db-tavily-key"
    # เก็บกวาด: กลับสู่ค่าว่าง (ใช้ .env จริงของเครื่องต่อ)
    put_app_settings(DSN, {"news_rss_feeds": ""})
    set_tavily_api_key(DSN, "")


@needs_pg
def test_tavily_key_protected_and_masked(client_p7):
    # ห้ามตั้ง ciphertext ผ่าน PUT ปกติ
    assert client_p7.put("/settings.json", json={"tavily_api_key_enc": "hack"}).status_code == 422
    # GET ไม่มี ciphertext รั่ว
    data = client_p7.get("/settings.json").json()
    assert "tavily_api_key_enc" not in data
    assert "news" in data and "feeds" in data["news"]


@pytest.fixture
def client_p7():
    from fastapi.testclient import TestClient

    from api.app import app

    return TestClient(app)
