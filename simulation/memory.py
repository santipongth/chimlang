"""Living Society Memory (SIM-05) — โลกจำลองของ workspace คงสถานะข้าม simulation

ตาม D4 (TECH-DECISIONS): PostgreSQL + schema เอง, interface ออกแบบให้สลับเป็น
Zep-compatible ได้ภายหลัง — ขอบเขต Phase 2 (dev): structured memory + recency recall;
คอลัมน์ embedding (pgvector) จองไว้แต่ยังไม่เปิดใช้ (บันทึกใน PHASE2-BRIEF —
semantic search เป็นงานตอน scale จริง อย่าสร้างก่อนจำเป็น)

ผลจริงของ "โลกจำได้":
- ผล simulation ก่อนหน้า (belief share) กลายเป็นจุดตั้งต้นของ run ถัดไป (ผ่าน engine.preseed)
- เหตุการณ์จริง/โน้ตผู้ใช้ซึมเข้า context — ทุกข้อความผ่าน PII detector ก่อนบันทึก (กฎเหล็กข้อ 1)
- reset world ได้ (ลบเฉพาะ workspace ตัวเอง + ลง audit เสมอ)
"""

from dataclasses import dataclass
from datetime import datetime

import psycopg

from governance.pii import PIIDetector

_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_memory (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    workspace TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('real_event', 'sim_result', 'user_note')),
    content TEXT NOT NULL,
    belief_share DOUBLE PRECISION,  -- เฉพาะ sim_result: สถานะโลกที่จะส่งต่อ run ถัดไป
    source_run_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS world_memory_ws_ts ON world_memory (workspace, ts DESC);
"""


class MemoryBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryItem:
    memory_id: int
    ts: datetime
    kind: str
    content: str
    belief_share: float | None
    source_run_id: str


class WorldMemory:
    def __init__(self, dsn: str, detector: PIIDetector):
        self._dsn = dsn
        self._detector = detector

    def _conn(self):
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def remember(
        self,
        workspace: str,
        kind: str,
        content: str,
        *,
        belief_share: float | None = None,
        source_run_id: str = "",
    ) -> None:
        """บันทึกความจำ — ข้อความทุกชิ้นผ่าน PII detector ก่อน (fail-closed)"""
        report = self._detector.check(content)
        if report.blocked:
            raise MemoryBlockedError(
                "memory ถูก block: พบ PII ในเนื้อหา (GOV-01) — " + "; ".join(report.block_reasons)
            )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO world_memory (workspace, kind, content, belief_share, source_run_id)"
                " VALUES (%s, %s, %s, %s, %s)",
                (workspace, kind, content, belief_share, source_run_id),
            )

    def recall(self, workspace: str, *, limit: int = 10) -> list[MemoryItem]:
        """ความจำล่าสุดของ workspace (ใหม่ → เก่า) — recency recall ระดับ Phase 2"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, ts, kind, content, belief_share, source_run_id FROM world_memory "
                "WHERE workspace = %s ORDER BY ts DESC, id DESC LIMIT %s",
                (workspace, limit),
            ).fetchall()
        return [MemoryItem(*row) for row in rows]

    def latest_belief(self, workspace: str) -> float | None:
        """สถานะความเชื่อล่าสุดของโลกนี้ — จุดตั้งต้นของ simulation ถัดไป (SIM-05)"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT belief_share FROM world_memory "
                "WHERE workspace = %s AND kind = 'sim_result' AND belief_share IS NOT NULL "
                "ORDER BY ts DESC, id DESC LIMIT 1",
                (workspace,),
            ).fetchone()
        return float(row[0]) if row else None

    def reset_world(self, workspace: str) -> int:
        """ล้างโลก (เฉพาะ workspace นี้) — memory เป็น working state ไม่ใช่ governance record
        แต่ผู้เรียกต้องลง audit ทุกครั้ง (script บังคับ)"""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM world_memory WHERE workspace = %s", (workspace,))
            return cur.rowcount


def render_memory_context(items: list[MemoryItem]) -> str:
    """แปลงความจำเป็น context ไทยสำหรับ prompt (ใหม่สุดก่อน)"""
    if not items:
        return "(โลกนี้ยังไม่มีความจำ)"
    kind_th = {"real_event": "เหตุการณ์จริง", "sim_result": "ผลจำลองก่อนหน้า", "user_note": "โน้ต"}
    return "\n".join(
        f"- [{kind_th.get(m.kind, m.kind)} {m.ts:%d/%m %H:%M}] {m.content}" for m in items
    )
