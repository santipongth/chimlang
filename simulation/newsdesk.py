"""News Desk กลาง (P7-M1/M2, SIM-11) — agent ได้ข้อมูลสดจากเน็ตผ่านโต๊ะข่าวเดียว ไม่ยิงเน็ตเอง

หลักออกแบบ (PHASE7-BRIEF):
- ทุก fetch ผ่าน gate hindcast (`ensure_external_retrieval_allowed`) — กฎเหล็กข้อ 2
- PII gate ทุกชิ้นแบบ fail-closed (GOV-01) — item ที่พบ PII ถูก block ทั้งชิ้น
- snapshot-first (NFR-07): เก็บลง DB ก่อนใช้ — replay อ่านจาก `load_items` เท่านั้น ไม่แตะเน็ต
- media diet (M2): แต่ละ segment เห็นข่าวถ่วงด้วย channel_mix ของกลุ่มตัวเอง = selective exposure
- Tavily search: key จาก .env (`TAVILY_API_KEY`) — ไม่มี key = โหมด RSS อย่างเดียว (degrade ไม่พัง)
"""

import hashlib
import json
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import psycopg

from core.config import get_settings
from core.run_context import RunContext, ensure_external_retrieval_allowed
from governance.pii import PIIDetector, load_allowlist
from simulation.sources import _parse_rss, _strip_html, _trigrams

MAX_ITEMS_PER_RUN = 30
MAX_SEARCH_QUERIES_PER_RUN = 8
MAX_CONTENT_CHARS = 4_000

# heuristic การกระจายข่าวเข้าช่องทาง (บันทึกตรงๆ ว่าเป็น heuristic จาก provider —
# ไม่ใช่ข้อมูลจริงว่าข่าวชิ้นนั้นแพร่ช่องไหน; refine ภายหลังได้โดยแก้ mapping นี้จุดเดียว)
CHANNEL_TAGS = {
    "rss": {"public_feed": 0.45, "line_closed_group": 0.25, "algo_feed": 0.20, "offline_wom": 0.10},
    "search": {
        "algo_feed": 0.45,
        "public_feed": 0.35,
        "line_closed_group": 0.15,
        "offline_wom": 0.05,
    },
}

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
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS news_items_run ON news_items (run_id);
"""


@dataclass(frozen=True)
class NewsItem:
    provider: str
    url: str
    title: str
    content: str
    fetched_at: str
    channel_tags: dict[str, float]
    status: str  # ready | blocked
    error: str = ""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _fetch_rss_items(feed_url: str) -> list[tuple[str, str]]:
    """คืน [(title, content)] จาก feed — แยกราย item เพื่อ PII gate เป็นชิ้นๆ"""
    resp = httpx.get(
        feed_url, timeout=15.0, follow_redirects=True, headers={"User-Agent": "chimlang/1.0"}
    )
    resp.raise_for_status()
    out: list[tuple[str, str]] = []
    for block in _parse_rss(resp.text).split("\n\n"):
        lines = block.strip().split("\n", 1)
        if lines and lines[0]:
            out.append((lines[0][:200], block.strip()[:MAX_CONTENT_CHARS]))
    return out


def _tavily_search(query: str, api_key: str, *, max_results: int = 3) -> list[tuple[str, str, str]]:
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


def gather(
    dsn: str,
    ctx: RunContext,
    *,
    feeds: list[str] | None = None,
    queries: list[str] | None = None,
) -> list[NewsItem]:
    """ดึงข่าวเข้าโต๊ะ + snapshot ลง DB — จุดเดียวที่แตะเน็ต (gate + PII ทุกชิ้น)

    fail-closed: hindcast = raise ก่อนแตะเน็ต; detector ปิด = ปฏิเสธ; item มี PII = block ทั้งชิ้น
    """
    ensure_external_retrieval_allowed(ctx)  # กฎเหล็กข้อ 2 — ก่อน I/O ใดๆ
    settings = get_settings()
    if not settings.pii_detector_enabled:
        raise ValueError("PII detector ถูกปิด — ปฏิเสธการดึงข่าว (GOV-01 fail-closed)")
    detector = PIIDetector(load_allowlist())
    feeds = feeds if feeds is not None else settings.news_rss_feeds_list()
    queries = list(queries or [])[:MAX_SEARCH_QUERIES_PER_RUN]

    raw: list[tuple[str, str, str, str, str]] = []  # (provider, query, url, title, content)
    for feed in feeds[:10]:
        try:
            for title, content in _fetch_rss_items(feed)[:10]:
                raw.append(("rss", feed, feed, title, content))
        except Exception:
            continue  # feed เสีย = ข้าม (ข่าวจากแหล่งอื่นยังใช้ได้)
    if queries and settings.tavily_api_key.strip():
        for q in queries:
            try:
                for title, url, content in _tavily_search(q, settings.tavily_api_key.strip()):
                    raw.append(("search", q, url, title, content))
            except Exception:
                continue

    items: list[NewsItem] = []
    seen: set[str] = set()
    now = datetime.now(UTC).isoformat()
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)
        for provider, query, url, title, content in raw:
            if len(items) >= MAX_ITEMS_PER_RUN:
                break
            h = _hash(title + content)
            if h in seen or not content.strip():
                continue
            seen.add(h)
            report = detector.check(f"{title}\n{content}")
            status, error = ("ready", "")
            stored_content = content
            if report.blocked:
                status = "blocked"
                error = "พบ PII (GOV-01): " + "; ".join(report.block_reasons[:3])
                stored_content = ""  # ไม่เก็บเนื้อหาที่มี PII
            tags = CHANNEL_TAGS[provider]
            conn.execute(
                "INSERT INTO news_items (run_id, provider, query, url, title, content, "
                "content_hash, channel_tags, status, error) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
                (
                    ctx.run_id,
                    provider,
                    query,
                    url,
                    title,
                    stored_content,
                    h,
                    json.dumps(tags),
                    status,
                    error,
                ),
            )
            items.append(NewsItem(provider, url, title, stored_content, now, tags, status, error))
    return items


def load_items(dsn: str, run_id: str) -> list[NewsItem]:
    """อ่าน snapshot จาก DB เท่านั้น — path สำหรับ replay/แสดงผล ไม่แตะเน็ต (NFR-07)"""
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)
        rows = conn.execute(
            "SELECT provider, url, title, content, fetched_at::text, channel_tags, status, error "
            "FROM news_items WHERE run_id = %s ORDER BY id",
            (run_id,),
        ).fetchall()
    return [NewsItem(r[0], r[1], r[2], r[3], r[4], dict(r[5]), r[6], r[7]) for r in rows]


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
    ready = [it for it in items if it.status == "ready" and it.content]
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
