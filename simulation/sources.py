"""Sources ต่อ run (P6-M3) — เอกสารอ้างอิงจริงป้อนเข้า debate engine (แนว GraphRAG Swarm)

ต่างจาก SwarmSight ต้นแบบ:
- **PII gate ทุกเอกสารก่อนเข้าระบบ** (GOV-01/ADR-0010) — URL/RSS redact และสแกนซ้ำ
  ก่อน persist; direct text, PII URL หรือ verification failure ถูก block
- retrieval ใช้ BM25 ภาษาไทย + pgvector cosine และ Reciprocal Rank Fusion; ถ้า embedding
  ไม่พร้อมจะ fallback เป็น BM25 พร้อม provenance ชัดเจน ห้ามอ้างว่าเป็น vector
- จำกัด ≤ 10 sources/run, เนื้อหา ≤ 2MB/ชิ้น (กัน DoS ตัวเอง)
"""

import hashlib
import ipaddress
import json
import math
import re
from urllib.parse import urlparse

from core.config import get_settings
from core.db import connection, require_schema
from core.llm.adapter import LLMAdapter
from core.observability import observe_retrieval, traced
from core.safe_fetch import SafeOutboundFetcher
from governance.pii import PIIDetector, PIIRedactionError, load_allowlist

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
CREATE TABLE IF NOT EXISTS run_chunk_embeddings (
    chunk_id BIGINT NOT NULL REFERENCES run_chunks(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    model TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dimension INT NOT NULL,
    embedding vector NOT NULL,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, model, dimension)
);
CREATE INDEX IF NOT EXISTS run_chunk_embeddings_run
    ON run_chunk_embeddings (run_id, model, dimension);
CREATE INDEX IF NOT EXISTS run_chunk_embeddings_hnsw_1536
    ON run_chunk_embeddings USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
    WHERE dimension = 1536;
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


def _parse_rss(xml: str) -> str:
    items = re.findall(r"<item[\s\S]*?</item>|<entry[\s\S]*?</entry>", xml, flags=re.IGNORECASE)
    parts = []
    for chunk in items[:15]:
        title = re.search(r"<title[^>]*>([\s\S]*?)</title>", chunk, flags=re.IGNORECASE)
        desc = re.search(
            r"<description[^>]*>([\s\S]*?)</description>|<summary[^>]*>([\s\S]*?)</summary>",
            chunk,
            flags=re.IGNORECASE,
        )
        t = re.sub(r"<!\[CDATA\[|\]\]>", "", title.group(1)) if title else ""
        d = re.sub(r"<!\[CDATA\[|\]\]>", "", (desc.group(1) or desc.group(2))) if desc else ""
        parts.append(f"{_strip_html(t)}\n{_strip_html(d)}")
    return "\n\n".join(parts)


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
    kind_score = {"text": 0.75, "url": 0.85, "rss": 0.8}.get(kind, 0.65)
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
    return _parse_rss(raw) if kind == "rss" else _strip_html(raw)


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

    URL/RSS redact-and-verify ก่อน persist; direct text ที่พบ PII ยัง block ตาม ADR-0010.
    """
    settings = get_settings()
    if not settings.pii_detector_enabled:
        raise ValueError("PII detector ถูกปิด — ปฏิเสธการนำเข้าเอกสาร (GOV-01 fail-closed)")
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"จำกัด {MAX_SOURCES} sources ต่อ run")
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


def _vector_literal(values: tuple[float, ...]) -> str:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("embedding มีค่าไม่ถูกต้อง")
    return "[" + ",".join(f"{value:.9g}" for value in values) + "]"


def index_run_embeddings(dsn: str, run_id: str, adapter: LLMAdapter) -> dict:
    """Embed each stored chunk once for the configured model and persist provenance."""

    if not adapter.supports_embeddings():
        return {"status": "unavailable", "reason": "embedding_model_not_configured", "indexed": 0}
    model = adapter.embedding_model
    dimension = adapter.embedding_dimension
    with connection(dsn) as conn:
        rows = conn.execute(
            "SELECT c.id, c.content FROM run_chunks c LEFT JOIN run_chunk_embeddings e "
            "ON e.chunk_id = c.id AND e.model = %s AND e.dimension = %s "
            "WHERE c.run_id = %s AND e.chunk_id IS NULL ORDER BY c.id LIMIT 500",
            (model, dimension, run_id),
        ).fetchall()
    if not rows:
        return {"status": "ready", "model": model, "dimension": dimension, "indexed": 0}
    indexed = 0
    model_version = model
    total_cost = 0.0
    with traced("retrieval.index_embeddings", run_id=run_id, chunks=len(rows)):
        for start in range(0, len(rows), 32):
            batch = rows[start : start + 32]
            result = adapter.embed([row[1] for row in batch])
            model_version = result.model
            total_cost += result.cost_usd
            with connection(dsn) as conn:
                conn.cursor().executemany(
                    "INSERT INTO run_chunk_embeddings "
                    "(chunk_id, run_id, model, model_version, dimension, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s::vector) "
                    "ON CONFLICT (chunk_id, model, dimension) DO NOTHING",
                    [
                        (
                            row[0],
                            run_id,
                            model,
                            model_version,
                            result.dimension,
                            _vector_literal(vector),
                        )
                        for row, vector in zip(batch, result.vectors, strict=True)
                    ],
                )
            indexed += len(batch)
    return {
        "status": "ready",
        "model": model,
        "model_version": model_version,
        "dimension": dimension,
        "indexed": indexed,
        "cost_usd": round(total_cost, 6),
        "index": "pgvector_hnsw" if dimension == 1536 else "pgvector_exact_dimension_unindexed",
    }


def _vector_scores(
    dsn: str,
    run_id: str,
    query: str,
    adapter: LLMAdapter | None,
) -> tuple[dict[int, float], dict]:
    if adapter is None or not adapter.supports_embeddings():
        return {}, {"status": "unavailable", "reason": "embedding_model_not_configured"}
    with connection(dsn) as conn:
        coverage = conn.execute(
            "SELECT count(*), count(e.chunk_id) FROM run_chunks c "
            "LEFT JOIN run_chunk_embeddings e ON e.chunk_id = c.id AND e.model = %s "
            "AND e.dimension = %s WHERE c.run_id = %s",
            (adapter.embedding_model, adapter.embedding_dimension, run_id),
        ).fetchone()
    if not coverage[0] or coverage[1] < coverage[0]:
        return {}, {
            "status": "unavailable",
            "reason": "embedding_coverage_incomplete",
            "embedded_chunks": coverage[1],
            "total_chunks": coverage[0],
        }
    result = adapter.embed([query])
    literal = _vector_literal(result.vectors[0])
    dimension = result.dimension
    distance = (
        "(embedding::vector(1536) <=> %s::vector(1536))"
        if dimension == 1536
        else "(embedding <=> %s::vector)"
    )
    with connection(dsn) as conn:
        rows = conn.execute(
            f"SELECT chunk_id, 1 - {distance} AS similarity "  # noqa: S608 - fixed SQL fragment
            "FROM run_chunk_embeddings WHERE run_id = %s AND model = %s AND dimension = %s "
            f"ORDER BY {distance} LIMIT 500",  # noqa: S608 - fixed SQL fragment
            (
                literal,
                run_id,
                adapter.embedding_model,
                dimension,
                literal,
            ),
        ).fetchall()
    return (
        {int(chunk_id): float(similarity) for chunk_id, similarity in rows},
        {
            "status": "ready",
            "model": adapter.embedding_model,
            "model_version": result.model,
            "dimension": dimension,
            "index": "pgvector_hnsw" if dimension == 1536 else "pgvector_exact_dimension_unindexed",
            "query_cost_usd": round(result.cost_usd, 6),
        },
    )


def _ranks(scores: dict[int, float]) -> dict[int, int]:
    return {
        chunk_id: rank
        for rank, (chunk_id, _) in enumerate(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])), start=1
        )
        if _ > 0
    }


def retrieve_evidence(
    dsn: str,
    run_id: str,
    query: str,
    *,
    k: int = 6,
    mode: str = "hybrid",
    embedding_adapter: LLMAdapter | None = None,
) -> list[dict]:
    """Retrieve with BM25/vector ranks and RRF, preserving effective-mode provenance."""
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
    if mode not in {"hybrid", "bm25", "vector"}:
        mode = "hybrid"
    bm25 = _bm25_scores([(r[0], r[1], r[2], r[3]) for r in rows], query)
    requested_mode = mode
    vector: dict[int, float] = {}
    vector_provenance: dict = {"status": "not_requested"}
    if mode in {"vector", "hybrid"}:
        try:
            with traced("retrieval.query", run_id=run_id, requested_mode=mode):
                vector, vector_provenance = _vector_scores(dsn, run_id, query, embedding_adapter)
        except Exception as exc:
            vector_provenance = {"status": "unavailable", "reason": type(exc).__name__}
    bm25_ranks = _ranks(bm25)
    vector_ranks = _ranks(vector)
    vector_ready = bool(vector_ranks)
    if mode == "bm25":
        mode_used = "bm25"
    elif mode == "vector" and vector_ready:
        mode_used = (
            "pgvector_hnsw" if vector_provenance.get("index") == "pgvector_hnsw" else "pgvector"
        )
    elif mode == "hybrid" and vector_ready:
        mode_used = "rrf_pgvector_bm25"
    else:
        mode_used = "bm25_fallback_embedding_unavailable"
    scored: list[dict] = []
    for chunk_id, label, seq, content, kind, quality, duplicate_of, status in rows:
        lexical, components = _lexical_score(label, content, query)
        bm = bm25.get(chunk_id, 0.0)
        if mode == "bm25" or not vector_ready:
            score = bm
        elif mode == "vector":
            score = vector.get(chunk_id, 0.0)
        else:
            # Reciprocal Rank Fusion is scale-independent, unlike adding cosine to BM25.
            score = (1 / (60 + bm25_ranks[chunk_id]) if chunk_id in bm25_ranks else 0) + (
                1 / (60 + vector_ranks[chunk_id]) if chunk_id in vector_ranks else 0
            )
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
                "score_components": {**components, "bm25": round(bm, 4)},
                "rank_components": {
                    "bm25_rank": bm25_ranks.get(chunk_id),
                    "vector_rank": vector_ranks.get(chunk_id),
                    "vector_similarity": round(vector.get(chunk_id, 0.0), 6),
                },
                "retrieval_mode": mode_used,
                "requested_mode": requested_mode,
                "embedding_provenance": vector_provenance,
                "note": "vector_unavailable_fell_back"
                if requested_mode in {"vector", "hybrid"} and not vector_ready
                else "",
            }
        )
    scored.sort(key=lambda x: (-x["score"], x["source_label"], x["seq"]))
    observe_retrieval(requested_mode, mode_used, "success" if scored else "empty")
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
