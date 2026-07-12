"""Public Gallery + agree/disagree votes (P5-M8) — CIT-02 ภาคขยาย + C13 จาก SwarmSight

เผยแพร่ผลรันสู่สาธารณะ + ให้ประชาชนโหวตเห็นด้วย/ไม่เห็นด้วย (wisdom of crowd
เทียบกับ swarm) — ออกแบบ fail-closed ตาม ADR-0004:

1. **Election scenario ห้ามแชร์เด็ดขาด** (เข้มกว่า aggregate-only — GOV-02): ผลเลือกตั้ง
   บนหน้าสาธารณะเสี่ยงถูกอ้างเป็นโพลจริงสูงสุด จึง block ทั้งใบ
2. **แชร์ = export** → ต้องสิทธิ์ EXPORT + watermark เปิดอยู่ (GOV-03) + PII gate หัวข้อ
3. **Snapshot frozen**: payload ถูกถ่ายสำเนา ณ เวลาแชร์ (NFR-07) — แก้ไม่ได้ ถอนแชร์ได้อย่างเดียว
4. **Votes ไม่เก็บตัวตน**: dedup ด้วย hash(ip+ua) ทางเดียว — ไม่เก็บ IP ดิบ (PDPA/NFR-04)
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from core.config import get_settings
from governance.election import ElectionModeError, ElectionPolicy, classify_scenario
from governance.pii import PIIDetector, load_allowlist
from governance.watermark import WATERMARK_LABEL, WatermarkDisabledError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gallery_shares (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    share_token TEXT NOT NULL UNIQUE,
    subject TEXT NOT NULL,
    agents INT NOT NULL,
    payload JSONB NOT NULL,
    watermark JSONB NOT NULL,
    created_by TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS gallery_votes (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    share_id BIGINT NOT NULL REFERENCES gallery_shares(id) ON DELETE CASCADE,
    vote TEXT NOT NULL CHECK (vote IN ('agree', 'disagree')),
    voter_hash TEXT NOT NULL,
    UNIQUE (share_id, voter_hash)
);
"""

# salt คงที่สำหรับ dedup เท่านั้น (ไม่ใช่ความลับ) — จุดประสงค์คือกันเก็บ ip ดิบ ไม่ใช่ crypto
_VOTER_SALT = "chimlang-gallery-v1"


def voter_hash(ip: str, user_agent: str) -> str:
    return hashlib.sha256(f"{_VOTER_SALT}|{ip}|{user_agent}".encode()).hexdigest()[:32]


def guard_share(subject: str) -> None:
    """ด่านก่อนแชร์สาธารณะ — ทุกข้อ fail-closed (ADR-0004)"""
    settings = get_settings()
    if not settings.watermark_enabled:
        raise WatermarkDisabledError()  # แชร์สาธารณะ = export (GOV-03)
    if ElectionPolicy(classify_scenario(subject)).active:
        raise ElectionModeError(
            "election scenario ห้ามเผยแพร่บน public gallery — เสี่ยงถูกอ้างเป็นโพลจริง (GOV-02/ADR-0004)"
        )
    if not settings.pii_detector_enabled:
        raise ValueError("PII detector ถูกปิด — ปฏิเสธการแชร์ (GOV-01 fail-closed)")
    report = PIIDetector(load_allowlist()).check(subject)
    if report.blocked:
        raise ValueError(
            "พบข้อมูลส่วนบุคคลในหัวข้อ — ถูก block ตาม GOV-01: " + "; ".join(report.block_reasons)
        )


@dataclass(frozen=True)
class GalleryItem:
    id: int
    share_token: str
    subject: str
    agents: int
    created_at: str
    payload: dict
    watermark: dict
    votes: dict  # {"agree": n, "disagree": n}


class GalleryStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def share(self, *, subject: str, agents: int, payload: dict, created_by: str) -> str:
        """แชร์ snapshot — guard_share ต้องผ่านก่อนเสมอ (เรียกจากชั้น API)"""
        token = uuid.uuid4().hex
        watermark = {
            "label": WATERMARK_LABEL,
            "labels": ["simulation_estimate", "not_field_poll", "aggregate_only"],
            "shared_at": datetime.now(UTC).isoformat(),
            "note": "snapshot ณ เวลาแชร์ — ตัวเลขไม่อัปเดตตามรันใหม่ (frozen, NFR-07)",
        }
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO gallery_shares "
                "(share_token, subject, agents, payload, watermark, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    token,
                    subject,
                    agents,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(watermark, ensure_ascii=False),
                    created_by,
                ),
            )
        return token

    def _votes_for(self, conn, share_ids: list[int]) -> dict[int, dict]:
        counts: dict[int, dict] = {sid: {"agree": 0, "disagree": 0} for sid in share_ids}
        if not share_ids:
            return counts
        rows = conn.execute(
            "SELECT share_id, vote, count(*) FROM gallery_votes "
            "WHERE share_id = ANY(%s) GROUP BY share_id, vote",
            (share_ids,),
        ).fetchall()
        for sid, vote, n in rows:
            counts[sid][vote] = int(n)
        return counts

    def list_public(self, limit: int = 30) -> list[GalleryItem]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, share_token, subject, agents, created_at, payload, watermark "
                "FROM gallery_shares WHERE active ORDER BY created_at DESC LIMIT %s",
                (limit,),
            ).fetchall()
            votes = self._votes_for(conn, [r[0] for r in rows])
        return [
            GalleryItem(
                id=r[0],
                share_token=r[1],
                subject=r[2],
                agents=r[3],
                created_at=r[4].isoformat(),
                payload=r[5],
                watermark=r[6],
                votes=votes[r[0]],
            )
            for r in rows
        ]

    def get(self, token: str) -> GalleryItem:
        found = [i for i in self.list_public(limit=500) if i.share_token == token]
        if not found:
            raise ValueError("ไม่พบรายการแชร์นี้ (อาจถูกถอนแล้ว)")
        return found[0]

    def unshare(self, token: str) -> None:
        """ถอนจากสาธารณะ — record ยังอยู่ (audit ได้) แค่ไม่แสดง"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE gallery_shares SET active = false WHERE share_token = %s", (token,)
            )

    def vote(self, token: str, vote: str, voter: str) -> dict:
        """1 คน (voter_hash) โหวตได้ 1 เสียงต่อรายการ — โหวตซ้ำ = เปลี่ยนเสียงเดิม"""
        if vote not in ("agree", "disagree"):
            raise ValueError("vote ต้องเป็น agree หรือ disagree")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM gallery_shares WHERE share_token = %s AND active", (token,)
            ).fetchone()
            if row is None:
                raise ValueError("ไม่พบรายการแชร์นี้")
            share_id = int(row[0])
            conn.execute(
                "INSERT INTO gallery_votes (share_id, vote, voter_hash) VALUES (%s, %s, %s) "
                "ON CONFLICT (share_id, voter_hash) DO UPDATE SET vote = EXCLUDED.vote, ts = now()",
                (share_id, vote, voter),
            )
            return self._votes_for(conn, [share_id])[share_id]
