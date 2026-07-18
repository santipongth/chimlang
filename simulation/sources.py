"""Sources ต่อ run (P6-M3) — เอกสารอ้างอิงจริงป้อนเข้า debate engine (แนว GraphRAG Swarm)

ต่างจาก SwarmSight ต้นแบบ:
- **PII gate ทุกเอกสารก่อนเข้าระบบ** (GOV-01/ADR-0010) — URL redact และสแกนซ้ำ
  ก่อน persist; direct text, PII URL หรือ verification failure ถูก block
- retrieval ใช้ BM25 ภาษาไทย + lexical scoring แบบ deterministic (ADR-0023: ถอด vector path แล้ว)
- จำกัด ≤ 10 sources/run, เนื้อหา ≤ 2MB/ชิ้น (กัน DoS ตัวเอง)
- kind รับเฉพาะ 'text' และ 'url' (ADR-0027 ถอด 'rss') — แถวประวัติ kind='rss' ยังอ่านได้
"""

import hashlib
import ipaddress
import json
import math
import re
from urllib.parse import urlparse

from core.config import get_settings
from core.db import connection, require_schema
from core.observability import observe_retrieval
from core.safe_fetch import SafeOutboundFetcher
from governance.pii import PIIDetector, PIIRedactionError, load_allowlist

# ADR-0027: evidence source รับเฉพาะ text/url — 'rss' ถูกถอดจากทางเข้าใหม่ทุกทาง
# (CHECK constraint ใน _SCHEMA ยังคง 'rss' ไว้เพื่อให้แถวประวัติ valid — ดู ADR-0027)
ALLOWED_SOURCE_KINDS = ("text", "url")
MAX_SOURCES = 10
MAX_TEXT_CHARS = 2_000_000
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
CACHE_TTL_HOURS = 6
BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_sources (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    -- 'rss' คงไว้ใน CHECK เพื่อให้แถวประวัติก่อน ADR-0027 valid เหมือนกันทุก deployment;
    -- ทางเข้าใหม่ถูกปฏิเสธที่ API (422) และ ingest_sources (ALLOWED_SOURCE_KINDS)
    kind TEXT NOT NULL CHECK (kind IN ('text', 'url', 'rss')),
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    chunks INT NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    duplicate_of TEXT NOT NULL DEFAULT '',
    quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    pii_redactions JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS run_chunks (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_label TEXT NOT NULL,
    seq INT NOT NULL,
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS run_chunks_run ON run_chunks (run_id);
CREATE TABLE IF NOT EXISTS external_fetch_cache (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    pii_redactions JSONB NOT NULL DEFAULT '{}',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def setup_sources(dsn: str) -> None:
    require_schema(dsn)


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _chunk(text: str) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    out = []
    i = 0
    while i < len(clean):
        out.append(clean[i : i + CHUNK_SIZE])
        if i + CHUNK_SIZE >= len(clean):
            break
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return out


def _quality_score(kind: str, text: str, chunks: int) -> float:
    length_score = min(1.0, len(text.strip()) / 2000)
    structure_score = 0.15 if re.search(r"https?://|^#{1,3}\s|\n[-*]\s", text, re.M) else 0.0
    kind_score = {"text": 0.75, "url": 0.85}.get(kind, 0.65)
    chunk_score = min(1.0, chunks / 4) * 0.15
    return round(
        max(0.0, min(1.0, kind_score * 0.55 + length_score * 0.3 + structure_score + chunk_score)),
        3,
    )


def validate_external_url(url: str) -> str:
    """URL guard กลางก่อน fetch user/admin-provided URL — ลด SSRF/localhost access."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("ต้องเป็น URL แบบ http(s)")
    host = parsed.hostname.strip().lower().rstrip(".")
    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise ValueError("URL ภายในเครื่องถูกปฏิเสธ")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return parsed.geturl()
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        raise ValueError("URL ไปยัง private/internal IP ถูกปฏิเสธ")
    return parsed.geturl()


def _fetch_text(kind: str, label: str, url: str | None, text: str | None) -> str:
    if kind == "text":
        return (text or "")[:MAX_TEXT_CHARS]
    safe_url = validate_external_url(url or "")
    raw = (
        SafeOutboundFetcher(
            max_compressed_bytes=MAX_TEXT_CHARS,
            max_bytes=MAX_TEXT_CHARS,
        )
        .fetch(safe_url)
        .text[:MAX_TEXT_CHARS]
    )
    return _strip_html(raw)


def _fetch_text_cached(
    conn,
    kind: str,
    label: str,
    url: str | None,
    text: str | None,
    detector: PIIDetector,
) -> tuple[str, dict[str, int]]:
    if kind == "text":
        content = _fetch_text(kind, label, url, text)
        report = detector.check(content)
        if report.blocked:
            raise PIIRedactionError("direct text evidence contains PII")
        return content, {}
    safe_url = validate_external_url(url or "")
    if detector.check(safe_url).blocked:
        raise PIIRedactionError("external evidence URL contains PII")
    url_hash = hashlib.sha256(f"{kind}:{safe_url}".encode()).hexdigest()
    row = conn.execute(
        "SELECT content, pii_redactions FROM external_fetch_cache "
        "WHERE url_hash = %s AND fetched_at > now() - (%s || ' hours')::interval",
        (url_hash, CACHE_TTL_HOURS),
    ).fetchone()
    if row:
        verified = detector.redact_and_verify(row[0])
        return verified.text, dict(row[1])
    raw_content = _fetch_text(kind, label, safe_url, text)
    redaction = detector.redact_and_verify(raw_content)
    conn.execute(
        "INSERT INTO external_fetch_cache "
        "(url_hash, url, kind, content, pii_redactions, fetched_at) "
        "VALUES (%s, %s, %s, %s, %s::jsonb, now()) "
        "ON CONFLICT (url_hash) DO UPDATE SET content = EXCLUDED.content, "
        "pii_redactions = EXCLUDED.pii_redactions, fetched_at = now(), "
        "url = EXCLUDED.url, kind = EXCLUDED.kind",
        (
            url_hash,
            safe_url,
            kind,
            redaction.text,
            json.dumps(redaction.counts),
        ),
    )
    return redaction.text, redaction.counts


def ingest_sources(dsn: str, run_id: str, sources: list[dict]) -> list[dict]:
    """นำเข้าเอกสารทั้งชุดของ run — คืนสถานะราย source

    URL redact-and-verify ก่อน persist; direct text ที่พบ PII ยัง block ตาม ADR-0010.
    kind รับเฉพาะ text/url (ADR-0027) — kind อื่นถูกปฏิเสธก่อนแตะ network/DB.
    """
    settings = get_settings()
    if not settings.pii_detector_enabled:
        raise ValueError("PII detector ถูกปิด — ปฏิเสธการนำเข้าเอกสาร (GOV-01 fail-closed)")
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"จำกัด {MAX_SOURCES} sources ต่อ run")
    for src in sources:
        if str(src.get("kind", "text")) not in ALLOWED_SOURCE_KINDS:
            raise ValueError("source kind ต้องเป็น text หรือ url เท่านั้น (ADR-0027 ถอด rss ออกแล้ว)")
    detector = PIIDetector(load_allowlist())
    results: list[dict] = []
    with connection(dsn) as conn:
        seen_hashes: dict[str, str] = {}
        for src in sources:
            kind = str(src.get("kind", "text"))
            requested_label = str(src.get("label", ""))[:200] or kind
            label_has_pii = detector.check(requested_label).blocked
            label = f"{kind}-source" if label_has_pii else requested_label
            status, error, n_chunks = "ready", "", 0
            content_hash, duplicate_of, quality_score = "", "", 0.0
            pii_redactions: dict[str, int] = {}
            try:
                if label_has_pii:
                    raise PIIRedactionError("source label contains PII")
                text, pii_redactions = _fetch_text_cached(
                    conn, kind, label, src.get("url"), src.get("text"), detector
                )
                if pii_redactions:
                    status = "redacted"
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if content_hash in seen_hashes:
                    status, duplicate_of = "duplicate", seen_hashes[content_hash]
                else:
                    chunks = _chunk(text)
                    if not chunks:
                        status = "empty"
                    else:
                        conn.cursor().executemany(
                            "INSERT INTO run_chunks (run_id, source_label, seq, content) "
                            "VALUES (%s, %s, %s, %s)",
                            [(run_id, label, i, c) for i, c in enumerate(chunks)],
                        )
                        n_chunks = len(chunks)
                        seen_hashes[content_hash] = label
                quality_score = _quality_score(kind, text, n_chunks)
            except PIIRedactionError:
                status, error = "blocked", "พบ PII ที่ redact อย่างปลอดภัยไม่ได้ (GOV-01)"
            except Exception as e:
                status = "error"
                try:
                    safe_error = detector.redact_and_verify(str(e)[:300])
                    error = safe_error.text
                    for pii_kind, count in safe_error.counts.items():
                        pii_redactions[pii_kind] = pii_redactions.get(pii_kind, 0) + count
                except PIIRedactionError:
                    error = "เกิดข้อผิดพลาดที่มี PII และไม่สามารถบันทึกรายละเอียดได้"
            conn.execute(
                "INSERT INTO run_sources "
                "(run_id, kind, label, status, error, chunks, content_hash, "
                "duplicate_of, quality_score, pii_redactions) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    run_id,
                    kind,
                    label,
                    status,
                    error,
                    n_chunks,
                    content_hash,
                    duplicate_of,
                    quality_score,
                    json.dumps(pii_redactions),
                ),
            )
            results.append(
                {
                    "label": label,
                    "kind": kind,
                    "status": status,
                    "error": error,
                    "chunks": n_chunks,
                    "content_hash": content_hash[:12],
                    "duplicate_of": duplicate_of,
                    "quality_score": quality_score,
                    "pii_redactions": pii_redactions,
                }
            )
    return results


def _trigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s)
    return {s[i : i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}


def _terms(s: str) -> set[str]:
    words = {w.lower() for w in re.findall(r"[\w\u0E00-\u0E7F]{3,}", s)}
    thai = re.sub(r"[^\u0E00-\u0E7F]", "", s)
    # Thai normally has no spaces, so character trigrams are BM25 terms too.
    return words | _trigrams(thai) if thai else words


def _term_counts(s: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for term in (w.lower() for w in re.findall(r"[\w\u0E00-\u0E7F]{3,}", s)):
        counts[term] = counts.get(term, 0) + 1
    thai = re.sub(r"[^\u0E00-\u0E7F]", "", s)
    for i in range(max(0, len(thai) - 2)):
        term = thai[i : i + 3]
        counts[term] = counts.get(term, 0) + 1
    return counts


def _citation_spans(content: str, query: str, *, max_spans: int = 4) -> list[dict]:
    spans: list[dict] = []
    lowered = content.lower()
    for term in sorted(_terms(query), key=len, reverse=True):
        start = lowered.find(term.lower())
        if start < 0:
            continue
        end = min(len(content), start + len(term))
        left = max(0, start - 42)
        right = min(len(content), end + 42)
        spans.append(
            {
                "start": start,
                "end": end,
                "text": content[left:right].strip(),
                "match": content[start:end],
            }
        )
        if len(spans) >= max_spans:
            break
    if not spans and content:
        spans.append(
            {"start": 0, "end": min(len(content), 120), "text": content[:120], "match": ""}
        )
    return spans


def _lexical_score(label: str, content: str, query: str) -> tuple[float, dict]:
    q = _trigrams(query)
    qt = _terms(query)
    trigram_hits = len(q & _trigrams(content))
    term_hits = len(qt & _terms(content))
    label_hits = len(qt & _terms(label))
    score = trigram_hits + 2 * term_hits + label_hits
    return float(score), {
        "trigram_hits": trigram_hits,
        "term_hits": term_hits,
        "label_hits": label_hits,
    }


def _bm25_scores(rows: list[tuple[int, str, int, str]], query: str) -> dict[int, float]:
    terms = _terms(query)
    if not terms or not rows:
        return {}
    docs = [(row[0], _term_counts(row[3])) for row in rows]
    avgdl = sum(sum(counts.values()) for _, counts in docs) / max(1, len(docs))
    out: dict[int, float] = {}
    for term in terms:
        df = sum(1 for _, counts in docs if term in counts)
        if not df:
            continue
        idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
        for chunk_id, counts in docs:
            tf = counts.get(term, 0)
            if not tf:
                continue
            dl = max(1, sum(counts.values()))
            denom = tf + 1.2 * (1 - 0.75 + 0.75 * dl / max(1, avgdl))
            out[chunk_id] = out.get(chunk_id, 0.0) + idf * (tf * 2.2 / denom)
    return out


def _ranks(scores: dict[int, float]) -> dict[int, int]:
    return {
        chunk_id: rank
        for rank, (chunk_id, _) in enumerate(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])), start=1
        )
        if _ > 0
    }


def retrieve_evidence(dsn: str, run_id: str, query: str, *, k: int = 6) -> list[dict]:
    """Retrieve ด้วย Thai BM25 + lexical scoring แบบ deterministic (ADR-0023: ถอด vector/RRF)"""
    try:
        with connection(dsn) as conn:
            rows = conn.execute(
                "SELECT c.id, c.source_label, c.seq, c.content, "
                "COALESCE(s.kind, 'text'), COALESCE(s.quality_score, 0), "
                "COALESCE(s.duplicate_of, ''), COALESCE(s.status, 'ready') "
                "FROM run_chunks c "
                "LEFT JOIN run_sources s ON s.run_id = c.run_id AND s.label = c.source_label "
                "WHERE c.run_id = %s LIMIT 500",
                (run_id,),
            ).fetchall()
    except Exception:
        return []
    if not rows:
        return []
    bm25 = _bm25_scores([(r[0], r[1], r[2], r[3]) for r in rows], query)
    bm25_ranks = _ranks(bm25)
    scored: list[dict] = []
    for chunk_id, label, seq, content, kind, quality, duplicate_of, status in rows:
        lexical, components = _lexical_score(label, content, query)
        score = bm25.get(chunk_id, 0.0)
        if score <= 0:
            continue
        scored.append(
            {
                "source_label": label,
                "seq": seq,
                "kind": kind,
                "status": status,
                "score": round(float(score), 4),
                "quality_score": float(quality or 0),
                "duplicate_of": duplicate_of,
                "content": content,
                "citation_spans": _citation_spans(content, query),
                "score_components": {**components, "bm25": round(score, 4)},
                "rank_components": {"bm25_rank": bm25_ranks.get(chunk_id)},
                "retrieval_mode": "bm25",
            }
        )
    scored.sort(key=lambda x: (-x["score"], x["source_label"], x["seq"]))
    observe_retrieval("bm25", "bm25", "success" if scored else "empty")
    return scored[:k]


def _retrieve_context_legacy(dsn: str, run_id: str, query: str, *, k: int = 6) -> tuple[str, ...]:
    """top-k chunks ของ run แบบ hybrid deterministic: 3-gram overlap + term overlap."""
    try:
        with connection(dsn) as conn:
            rows = conn.execute(
                "SELECT source_label, content FROM run_chunks WHERE run_id = %s LIMIT 500",
                (run_id,),
            ).fetchall()
    except Exception:
        return ()
    if not rows:
        return ()
    q = _trigrams(query)
    qt = _terms(query)
    scored = sorted(
        (
            (
                len(q & _trigrams(content))
                + 2 * len(qt & _terms(content))
                + len(qt & _terms(label)),
                content,
            )
            for label, content in rows
        ),
        key=lambda x: -x[0],
    )
    return tuple(content for score, content in scored[:k] if score > 0)


def retrieve_context(dsn: str, run_id: str, query: str, *, k: int = 6) -> tuple[str, ...]:
    """Backward-compatible context wrapper backed by rich retrieval."""
    return tuple(item["content"] for item in retrieve_evidence(dsn, run_id, query, k=k))
