"""News Desk กลาง (P7-M1/M2, SIM-11) — agent ได้ข้อมูลสดจากเน็ตผ่านโต๊ะข่าวเดียว ไม่ยิงเน็ตเอง

หลักออกแบบ (PHASE7-BRIEF + ADR-0026):
- ทุก fetch ผ่าน gate hindcast (`ensure_external_retrieval_allowed`) — กฎเหล็กข้อ 2
- PII gate ทุกชิ้นแบบ fail-closed (GOV-01/ADR-0010) — body/title redact+ตรวจซ้ำก่อน persist;
  URL PII หรือ verification failure ถูก block
- snapshot-first (NFR-07): เก็บลง DB ก่อนใช้ — replay อ่านจาก `load_items` เท่านั้น ไม่แตะเน็ต
- media diet (M2): แต่ละ segment เห็นข่าวถ่วงด้วย channel_mix ของกลุ่มตัวเอง = selective exposure
- provider เดียว: Tavily search (ADR-0026 ถอด RSS ออกทั้งหมด) — key จาก .env/Settings
  (`TAVILY_API_KEY`); ไม่มี key = บันทึก skipped evidence (ไม่มีข่าวเข้า run)
"""

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from core.config import get_settings
from core.db import connection, require_schema
from core.run_context import RunContext, ensure_external_retrieval_allowed
from governance.pii import PIIDetector, PIIRedactionError, load_allowlist
from simulation.sources import _bm25_scores, _strip_html, _trigrams

MAX_ITEMS_PER_RUN = 30
MAX_SEARCH_QUERIES_PER_RUN = 8
MAX_CONTENT_CHARS = 4_000
# จำนวนผลลัพธ์ต่อคำค้นจาก Tavily — คุมทั้ง latency และปริมาณเนื้อหาที่ต้องผ่าน PII gate;
# ค่าคงที่โดยเจตนา (ไม่เป็น setting) เพราะ caps ต่อ run ข้างบนเป็นด่านคุมปริมาณจริงอยู่แล้ว
TAVILY_MAX_RESULTS = 3
NEWS_CACHE_TTL_HOURS = 6  # default — ปรับได้จากหน้า Settings (news_cache_ttl_hours)
# ตัดซ้ำแบบใกล้เคียงด้วย containment coefficient (|A∩B| / min(|A|,|B|)) แทน Jaccard —
# ข่าวเรื่องเดียวกันคนละสำนักมักเป็น "เนื้อเดิม + พาดหัว/รายละเอียดต่างกัน" ซึ่ง Jaccard เจือจาง
NEAR_DUP_CONTAINMENT = 0.7

# heuristic การกระจายข่าวเข้าช่องทาง (บันทึกตรงๆ ว่าเป็น heuristic จาก provider —
# ไม่ใช่ข้อมูลจริงว่าข่าวชิ้นนั้นแพร่ช่องไหน; refine ภายหลังได้โดยแก้ mapping นี้จุดเดียว)
# หมายเหตุ ADR-0026: เหลือ provider 'search' เท่านั้น — แถวเก่า provider 'rss' ใน DB
# ยังอ่านได้ตามเดิม (load_items คืน channel_tags ที่ snapshot ไว้กับแถว ไม่พึ่งตารางนี้)
CHANNEL_TAGS = {
    "search": {
        "algo_feed": 0.45,
        "public_feed": 0.35,
        "line_closed_group": 0.15,
        "offline_wom": 0.05,
    },
}

# CHECK (provider IN ('rss', 'search')) คงไว้ทั้งสองตาราง — แถวเก่า provider='rss'
# เป็น snapshot ประวัติที่ต้องอ่านได้ต่อ (ADR-0026)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS news_items (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('rss', 'search')),
    query TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel_tags JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    pii_redactions JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS news_items_run ON news_items (run_id);
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS pii_redactions JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS news_fetch_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('rss', 'search')),
    query TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS news_fetch_cache_fetched ON news_fetch_cache (fetched_at);
"""


@dataclass(frozen=True)
class NewsItem:
    provider: str
    url: str
    title: str
    content: str
    fetched_at: str
    channel_tags: dict[str, float]
    status: str  # ready | redacted | blocked | error | skipped
    error: str = ""
    pii_redactions: dict[str, int] = field(default_factory=dict)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


# วลี boilerplate ของหน้าเว็บ (cookie banner / เมนู / บล็อกแนะนำ) ที่ Tavily มักคืนติดมากับเนื้อ
# ข่าว — จับด้วย heuristic แล้วทิ้ง เพราะเป็น nav cruft ไม่ใช่เนื้อข่าวจริง (agent เคยบ่นว่า
# "ฟีดมีแต่ข่าวคุกกี้"). ตัวพิมพ์เล็กแล้วเทียบ (ภาษาไทยไม่มี case, อังกฤษถูก normalize)
_BOILERPLATE_PHRASES = (
    "ใช้คุกกี้",
    "cookie",
    "อ่านเพิ่มเติม",
    "ข่าวยอดนิยม",
    "เนื้อหาที่เกี่ยวข้อง",
    "ข่าวแนะนำ",
    "ยอมรับทั้งหมด",
    "นโยบายความเป็นส่วนตัว",
)
# เนื้อหาสั้นกว่านี้ถือว่าไม่พอเป็นข่าวจริง (พาดหัว/ป้ายเมนูล้วน) — ตัดทิ้ง
# ตั้งค่อนข้างต่ำ: ตัวกรองหลักคือวลี boilerplate + BM25 relevance; length เป็นด่านรอง
_MIN_CONTENT_CHARS = 24


def _is_low_quality(title: str, content: str) -> bool:
    """True = search result เป็น boilerplate/nav cruft หรือเนื้อหาสั้นเกินจะเป็นข่าวจริง"""
    body = str(content or "").strip()
    if len(body) < _MIN_CONTENT_CHARS:
        return True
    haystack = f"{title or ''} {body}".lower()
    return any(phrase in haystack for phrase in _BOILERPLATE_PHRASES)


def _rank_search_items(raw: list[dict], topic: str) -> list[dict]:
    """กรอง boilerplate + จัดอันดับผลค้นตามความเข้ากับหัวข้อ (BM25 เทียบ topic)

    - ready/redacted: ผ่านตัวกรอง boilerplate แล้วให้คะแนน BM25 เทียบ topic → เก็บเฉพาะที่คะแนน>0
      (off-topic เช่น แทคติกเกม/พรีเมียร์ลีก คะแนน ~0 ถูกตัด) เรียงมากไปน้อย
    - blocked/error/skipped: ไม่เข้าคิวจัดอันดับ — ผ่านตรงเพื่อคง snapshot เป็นหลักฐาน (auditability)
    """
    passthrough = [r for r in raw if r.get("status") not in ("ready", "redacted")]
    rankable = [
        r
        for r in raw
        if r.get("status") in ("ready", "redacted")
        and not _is_low_quality(r.get("title", ""), r.get("content", ""))
    ]
    if not topic.strip() or not rankable:
        return rankable + passthrough
    rows = [
        (idx, "", 0, f"{r.get('title', '')} {r.get('content', '')}")
        for idx, r in enumerate(rankable)
    ]
    scores = _bm25_scores(rows, topic)
    kept = [
        (scores.get(idx, 0.0), idx, r) for idx, r in enumerate(rankable) if scores.get(idx, 0.0) > 0
    ]
    kept.sort(key=lambda item: (-item[0], item[1]))
    return [r for _, _, r in kept] + passthrough


def _tavily_search(
    query: str, api_key: str, *, max_results: int = TAVILY_MAX_RESULTS
) -> list[tuple[str, str, str]]:
    """คืน [(title, url, content)] — เรียก Tavily REST (คุณภาพไทยยังไม่ benchmark — ดู brief)"""
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": max_results},
        timeout=20.0,
    )
    resp.raise_for_status()
    return [
        (
            str(r.get("title", ""))[:200],
            str(r.get("url", "")),
            _strip_html(str(r.get("content", "")))[:MAX_CONTENT_CHARS],
        )
        for r in resp.json().get("results", [])
    ]


def setup_newsdesk(dsn: str) -> None:
    require_schema(dsn)


def _cache_key(provider: str, query: str, url: str) -> str:
    return _hash(f"{provider}\n{query}\n{url}")


def _prepare_news_payload(provider: str, payload: list, detector: PIIDetector) -> list[dict]:
    prepared: list[dict] = []
    for raw in payload:
        if isinstance(raw, dict):
            title = str(raw.get("title", ""))[:200]
            url = str(raw.get("url", ""))
            content = str(raw.get("content", ""))[:MAX_CONTENT_CHARS]
            prior_counts = {str(k): int(v) for k, v in (raw.get("pii_redactions") or {}).items()}
            prior_status = str(raw.get("status", "ready"))
        else:
            title, url, content = (str(x) for x in raw[:3])
            prior_counts, prior_status = {}, "ready"

        if url and detector.check(url).blocked:
            prepared.append(
                {
                    "title": "ข่าวถูกระงับจาก PII",
                    "url": "",
                    "content": "",
                    "status": "blocked",
                    "error": "พบ PII ใน URL (GOV-01)",
                    "pii_redactions": {},
                }
            )
            continue

        try:
            redaction = detector.redact_and_verify(f"{title}\n{content}")
        except PIIRedactionError:
            prepared.append(
                {
                    "title": "ข่าวถูกระงับจาก PII",
                    "url": url,
                    "content": "",
                    "status": "blocked",
                    "error": "พบ PII ที่ redact อย่างปลอดภัยไม่ได้ (GOV-01)",
                    "pii_redactions": {},
                }
            )
            continue

        safe_title, _, safe_content = redaction.text.partition("\n")
        counts = dict(prior_counts)
        for kind, count in redaction.counts.items():
            counts[kind] = counts.get(kind, 0) + count
        status = prior_status
        if status not in ("blocked", "error", "skipped"):
            status = "redacted" if counts else "ready"
        prepared.append(
            {
                "title": safe_title[:200],
                "url": url,
                "content": safe_content[:MAX_CONTENT_CHARS],
                "status": status,
                "error": str(raw.get("error", ""))[:500] if isinstance(raw, dict) else "",
                "pii_redactions": counts,
            }
        )
    return prepared


def _cached_fetch(
    dsn: str,
    *,
    provider: str,
    query: str,
    url: str,
    fetcher,
    detector: PIIDetector,
    ttl_hours: int = NEWS_CACHE_TTL_HOURS,
) -> list:
    if detector.check(f"{query}\n{url}").blocked:
        raise PIIRedactionError("news query or URL contains PII")
    key = _cache_key(provider, query, url)
    with connection(dsn) as conn:
        row = conn.execute(
            "SELECT payload, fetched_at FROM news_fetch_cache WHERE cache_key = %s",
            (key,),
        ).fetchone()
        if row and row[1] > datetime.now(UTC) - timedelta(hours=max(1, ttl_hours)):
            return _prepare_news_payload(provider, list(row[0]), detector)
    payload = _prepare_news_payload(provider, list(fetcher()), detector)
    with connection(dsn) as conn:
        conn.execute(
            "INSERT INTO news_fetch_cache (cache_key, provider, query, url, payload, fetched_at) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, now()) "
            "ON CONFLICT (cache_key) DO UPDATE SET payload = EXCLUDED.payload, "
            "fetched_at = now()",
            (key, provider, query, url, json.dumps(payload, ensure_ascii=False)),
        )
    return list(payload)


def effective_news_config(settings) -> str:
    """Tavily key ที่ใช้จริง — ค่าจากหน้า Settings (DB) ทับ .env; DB ไม่พร้อม = .env"""
    key = settings.tavily_api_key.strip()
    try:
        from core.appsettings import get_tavily_api_key

        db_key = get_tavily_api_key(settings.postgres_url)
        if db_key:
            key = db_key
    except Exception:
        pass  # fail-safe: DB/ถอดรหัสพัง = ใช้ .env ต่อ (ไม่ block งาน)
    return key


def effective_news_tuning(settings) -> tuple[int, int]:
    """(cache_ttl_hours, tavily_max_results) ที่ใช้จริง — ค่าจาก Settings (DB, 0 = default) ทับ .env"""
    ttl = int(settings.news_cache_ttl_hours)
    max_results = int(settings.tavily_max_results)
    try:
        from core.appsettings import get_app_settings

        data = get_app_settings(settings.postgres_url)
        if int(data.get("news_cache_ttl_hours") or 0) > 0:
            ttl = int(data["news_cache_ttl_hours"])
        if int(data.get("tavily_max_results") or 0) > 0:
            max_results = int(data["tavily_max_results"])
    except Exception:
        pass  # fail-safe: DB พัง = ใช้ .env ต่อ
    return max(1, ttl), max(1, max_results)


def gather(
    dsn: str,
    ctx: RunContext,
    *,
    queries: list[str] | None = None,
) -> list[NewsItem]:
    """ดึงข่าวเข้าโต๊ะ + snapshot ลง DB — จุดเดียวที่แตะเน็ต (gate + PII ทุกชิ้น)

    Tavily search เท่านั้น (ADR-0026) — จัดอันดับตามคำค้นโดย provider อยู่แล้ว.
    Body/title redact-and-verify ก่อน persist; URL PII หรือ verification fail = block.
    """
    ensure_external_retrieval_allowed(ctx)  # กฎเหล็กข้อ 2 — ก่อน I/O ใดๆ
    settings = get_settings()
    if not settings.pii_detector_enabled:
        raise ValueError("PII detector ถูกปิด — ปฏิเสธการดึงข่าว (GOV-01 fail-closed)")
    detector = PIIDetector(load_allowlist())
    tavily_key = effective_news_config(settings)
    ttl_hours, max_results = effective_news_tuning(settings)
    queries = list(queries or [])[:MAX_SEARCH_QUERIES_PER_RUN]

    raw: list[dict] = []
    failures: list[tuple[str, str, str, str]] = []  # (provider, query, url, error)
    if queries and tavily_key:
        for q in queries:
            try:
                results = _cached_fetch(
                    dsn,
                    provider="search",
                    query=q,
                    url="https://api.tavily.com/search",
                    fetcher=lambda q=q: _tavily_search(q, tavily_key, max_results=max_results),
                    detector=detector,
                    ttl_hours=ttl_hours,
                )
                for item in results:
                    raw.append({"provider": "search", "query": q, **item})
            except PIIRedactionError:
                failures.append(("search", "", "", "พบ PII ในคำค้นหรือ URL (GOV-01)"))
            except Exception as e:
                failures.append(("search", q, "", f"Tavily search failed: {type(e).__name__}: {e}"))
    elif queries and not tavily_key:
        for q in queries:
            failures.append(("search", q, "", "Tavily skipped: TAVILY_API_KEY ยังไม่ได้ตั้งค่า"))

    # กรอง boilerplate + จัดอันดับผลค้นตามหัวข้อ run (queries[0]) ก่อนเข้าเพดาน MAX_ITEMS_PER_RUN;
    # off-topic/ขยะ (คะแนน BM25 ~0) ถูกตัด. blocked/error/skipped ไม่แตะ (คง snapshot เป็นหลักฐาน)
    raw = _rank_search_items(raw, queries[0] if queries else "")

    items: list[NewsItem] = []
    seen: set[str] = set()
    seen_grams: list[frozenset] = []
    now = datetime.now(UTC).isoformat()
    with connection(dsn) as conn:
        for provider, query, url, error in failures:
            if len(items) >= MAX_ITEMS_PER_RUN:
                break
            try:
                safe_error = detector.redact_and_verify(error[:500])
                error = safe_error.text
                pii_redactions = safe_error.counts
            except PIIRedactionError:
                error = "เกิดข้อผิดพลาดที่มี PII และไม่สามารถบันทึกรายละเอียดได้"
                pii_redactions = {}
            tags = CHANNEL_TAGS[provider]
            title = "ค้นหาข่าวไม่สำเร็จ"
            h = _hash(provider + query + url + error)
            status = (
                "blocked"
                if "GOV-01" in error
                else ("skipped" if "skipped" in error.lower() else "error")
            )
            conn.execute(
                "INSERT INTO news_items (run_id, provider, query, url, title, content, "
                "content_hash, channel_tags, status, error, pii_redactions) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)",
                (
                    ctx.run_id,
                    provider,
                    query,
                    url,
                    title,
                    "",
                    h,
                    json.dumps(tags),
                    status,
                    error[:500],
                    json.dumps(pii_redactions),
                ),
            )
            items.append(
                NewsItem(provider, url, title, "", now, tags, status, error[:500], pii_redactions)
            )
        for raw_item in raw:
            if len(items) >= MAX_ITEMS_PER_RUN:
                break
            provider = raw_item["provider"]
            query = raw_item["query"]
            url = raw_item["url"]
            title = raw_item["title"]
            content = raw_item["content"]
            status = raw_item["status"]
            error = raw_item["error"]
            pii_redactions = raw_item["pii_redactions"]
            h = _hash(title + content)
            if h in seen or (status in ("ready", "redacted") and not content.strip()):
                continue
            if status in ("ready", "redacted"):
                # ตัดซ้ำแบบใกล้เคียง: ข่าวเรื่องเดียวกันคนละสำนัก (ถ้อยคำต่างเล็กน้อย)
                # ใช้ 3-gram Jaccard เกณฑ์เดียวกับ dedupe_intents — ไม่เผาโควตา 30 ชิ้นซ้ำ
                grams = frozenset(_trigrams(f"{title} {content[:400]}"))
                if grams and any(
                    len(grams & other) / (min(len(grams), len(other)) or 1) > NEAR_DUP_CONTAINMENT
                    for other in seen_grams
                ):
                    continue
                if grams:
                    seen_grams.append(grams)
            seen.add(h)
            tags = CHANNEL_TAGS[provider]
            conn.execute(
                "INSERT INTO news_items (run_id, provider, query, url, title, content, "
                "content_hash, channel_tags, status, error, pii_redactions) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)",
                (
                    ctx.run_id,
                    provider,
                    query,
                    url,
                    title,
                    content,
                    h,
                    json.dumps(tags),
                    status,
                    error,
                    json.dumps(pii_redactions),
                ),
            )
            items.append(
                NewsItem(
                    provider,
                    url,
                    title,
                    content,
                    now,
                    tags,
                    status,
                    error,
                    pii_redactions,
                )
            )
    return items


def load_items(dsn: str, run_id: str) -> list[NewsItem]:
    """อ่าน snapshot จาก DB เท่านั้น — path สำหรับ replay/แสดงผล ไม่แตะเน็ต (NFR-07)

    แถวเก่า provider='rss' (ก่อน ADR-0026) ยังอ่านได้ตามเดิม — channel_tags มากับแถว
    """
    with connection(dsn) as conn:
        rows = conn.execute(
            "SELECT provider, url, title, content, fetched_at::text, channel_tags, status, error, "
            "pii_redactions "
            "FROM news_items WHERE run_id = %s ORDER BY id",
            (run_id,),
        ).fetchall()
    return [
        NewsItem(r[0], r[1], r[2], r[3], r[4], dict(r[5]), r[6], r[7], dict(r[8])) for r in rows
    ]


def segment_feed(
    items: list[NewsItem],
    channel_mix: dict[str, float],
    subject: str,
    *,
    k: int = 4,
    seed: int = 0,
) -> list[NewsItem]:
    """Media diet (M2): ข่าว top-k ที่ "กลุ่มนี้" เห็น — ถ่วง channel_mix × relevance × ลำดับความสด

    deterministic ต่อ (items, mix, subject, seed) — ไม่มีเน็ต ไม่มี I/O
    """
    ready = [it for it in items if it.status in ("ready", "redacted") and it.content]
    if not ready:
        return []
    q = _trigrams(subject)
    rng = random.Random(seed)
    scored: list[tuple[float, float, NewsItem]] = []
    for idx, it in enumerate(ready):
        # ความเข้ากันของช่องทาง: dot product ระหว่าง diet ของกลุ่มกับ tags ของข่าว
        channel_fit = sum(channel_mix.get(ch, 0.0) * w for ch, w in it.channel_tags.items())
        overlap = len(q & _trigrams(it.title + it.content[:400]))
        relevance = overlap / (len(q) or 1)
        freshness = 1.0 - (idx / max(1, len(ready))) * 0.3  # item ต้นลิสต์ = ใหม่กว่าเล็กน้อย
        score = channel_fit * (0.4 + relevance) * freshness
        scored.append((score, rng.random(), it))  # tie-break ด้วย rng ที่ seeded
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [it for _, _, it in scored[:k]]


def dedupe_intents(intents: list[str], *, cap: int = 3) -> list[str]:
    """รวบ query intent จาก agent หลายตัว → คำค้นไม่ซ้ำ จำกัดจำนวน (คุมงบ search)"""
    out: list[str] = []
    seen: set[frozenset] = set()
    for q in intents:
        q = re.sub(r"\s+", " ", q).strip()[:120]
        if len(q) < 4:
            continue
        key = frozenset(_trigrams(q))
        if any(len(key & s) / (len(key | s) or 1) > 0.6 for s in seen):
            continue  # ใกล้เคียงของเดิม = ข้าม
        seen.add(key)
        out.append(q)
        if len(out) >= cap:
            break
    return out
