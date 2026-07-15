"""Sources ต่อ run (P6-M3) — เอกสารอ้างอิงจริงป้อนเข้า debate engine (แนว GraphRAG Swarm)

ต่างจาก SwarmSight ต้นแบบ:
- **PII gate ทุกเอกสารก่อนเข้าระบบ** (GOV-01 fail-closed) — เอกสารที่พบ PII ถูก block
  ทั้งชิ้นพร้อมบันทึกเหตุผล (ต้นแบบรับตรงๆ)
- retrieval เป็น **lexical 3-gram overlap** (เหมาะกับไทยที่ไม่มีวรรคคำ ไม่ต้องพึ่ง tokenizer) —
  ยังไม่ใช่ vector search เพราะ stack ยังไม่มี embedding model (บันทึกใน PHASE6-BRIEF
  เป็นงานอนาคต — เปลี่ยนภายในฟังก์ชันเดียวโดยไม่แตะผู้เรียก)
- จำกัด ≤ 10 sources/run, เนื้อหา ≤ 2MB/ชิ้น (กัน DoS ตัวเอง)
"""

import hashlib
import ipaddress
import re
from urllib.parse import urlparse

import httpx
import psycopg

from core.config import get_settings
from governance.pii import PIIDetector, load_allowlist

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
    chunks INT NOT NULL DEFAULT 0
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
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def setup_sources(dsn: str) -> None:
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)


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
    resp = httpx.get(
        safe_url, timeout=15.0, follow_redirects=True, headers={"User-Agent": "chimlang/1.0"}
    )
    resp.raise_for_status()
    raw = resp.text[:MAX_TEXT_CHARS]
    return _parse_rss(raw) if kind == "rss" else _strip_html(raw)


def _fetch_text_cached(conn, kind: str, label: str, url: str | None, text: str | None) -> str:
    if kind == "text":
        return _fetch_text(kind, label, url, text)
    safe_url = validate_external_url(url or "")
    url_hash = hashlib.sha256(f"{kind}:{safe_url}".encode()).hexdigest()
    row = conn.execute(
        "SELECT content FROM external_fetch_cache "
        "WHERE url_hash = %s AND fetched_at > now() - (%s || ' hours')::interval",
        (url_hash, CACHE_TTL_HOURS),
    ).fetchone()
    if row:
        return row[0]
    content = _fetch_text(kind, label, safe_url, text)
    conn.execute(
        "INSERT INTO external_fetch_cache (url_hash, url, kind, content, fetched_at) "
        "VALUES (%s, %s, %s, %s, now()) "
        "ON CONFLICT (url_hash) DO UPDATE SET content = EXCLUDED.content, "
        "fetched_at = now(), url = EXCLUDED.url, kind = EXCLUDED.kind",
        (url_hash, safe_url, kind, content),
    )
    return content


def ingest_sources(dsn: str, run_id: str, sources: list[dict]) -> list[dict]:
    """นำเข้าเอกสารทั้งชุดของ run — คืนสถานะราย source (ready/blocked/error/empty)

    fail-closed: detector ปิด = ปฏิเสธทั้งชุด; เอกสารที่พบ PII = block ทั้งชิ้น
    """
    settings = get_settings()
    if not settings.pii_detector_enabled:
        raise ValueError("PII detector ถูกปิด — ปฏิเสธการนำเข้าเอกสาร (GOV-01 fail-closed)")
    if len(sources) > MAX_SOURCES:
        raise ValueError(f"จำกัด {MAX_SOURCES} sources ต่อ run")
    detector = PIIDetector(load_allowlist())
    results: list[dict] = []
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)
        for src in sources:
            kind = str(src.get("kind", "text"))
            label = str(src.get("label", ""))[:200] or kind
            status, error, n_chunks = "ready", "", 0
            try:
                text = _fetch_text_cached(conn, kind, label, src.get("url"), src.get("text"))
                report = detector.check(text)
                if report.blocked:
                    status, error = (
                        "blocked",
                        "พบ PII (GOV-01): " + "; ".join(report.block_reasons[:5]),
                    )
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
            except Exception as e:
                status, error = "error", str(e)[:300]
            conn.execute(
                "INSERT INTO run_sources (run_id, kind, label, status, error, chunks) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (run_id, kind, label, status, error, n_chunks),
            )
            results.append(
                {"label": label, "kind": kind, "status": status, "error": error, "chunks": n_chunks}
            )
    return results


def _trigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", s)
    return {s[i : i + 3] for i in range(len(s) - 2)} if len(s) >= 3 else {s}


def _terms(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[\w\u0E00-\u0E7F]{3,}", s)}


def retrieve_context(dsn: str, run_id: str, query: str, *, k: int = 6) -> tuple[str, ...]:
    """top-k chunks ของ run แบบ hybrid deterministic: 3-gram overlap + term overlap."""
    try:
        with psycopg.connect(dsn) as conn:
            conn.execute(_SCHEMA)
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
