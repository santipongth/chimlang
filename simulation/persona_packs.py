"""Persona Packs (P5-M7 — backlog Group A จาก SwarmSight): audience ที่ผู้ใช้นิยามเอง

ผู้ใช้สร้าง "pack" = ชุด segment (สัดส่วน + cultural priors + channel mix) แล้ว reuse
กับทุกโหมด (dashboard / compare / watchlist) — โครงเดียวกับ segments.yaml ของ factory
เพื่อให้ `PersonaFactory(segments=...)` ใช้ได้ตรงๆ ไม่ต้องแตะ engine

Governance:
- GOV-01: ทุกข้อความใน pack (label/ชื่อ segment/traits) ผ่าน PII detector — พบ = block
  และ detector ถูกปิด = ปฏิเสธทั้ง operation (fail-closed เหมือน ingest pipeline)
- pack เป็นตาราง operational (แก้/ลบได้) — provenance ของ pack คือ prompt + ผู้สร้าง
  ที่เก็บคู่กันเสมอ (TRUST-06: persona ต้องบอกที่มาได้)
"""

import json
from dataclasses import dataclass

import psycopg

from core.config import get_settings
from governance.pii import PIIDetector, load_allowlist

VALID_CHANNELS = ("line_closed_group", "public_feed", "algo_feed", "offline_wom")
PRIOR_KEYS = ("kreng_jai", "say_do_gap", "sarcasm_meme")
# ขอบเขตจำนวนกลุ่ม: เหตุผลเชิงสถิติ (n≥30/กลุ่ม ที่ cap 1,000 agents) + practice segmentation — ดู ADR-0009
MIN_SEGMENTS, MAX_SEGMENTS = 2, 12

_SCHEMA = """
CREATE TABLE IF NOT EXISTS persona_packs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    label TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    segments JSONB NOT NULL
);
"""


class PackValidationError(ValueError):
    pass


class PIIInPackError(PackValidationError):
    def __init__(self, reasons: list[str]):
        super().__init__(
            "พบข้อมูลส่วนบุคคลใน persona pack — ถูก block ตาม GOV-01: " + "; ".join(reasons)
        )


def _pack_text(label: str, segments: list[dict]) -> str:
    """รวมข้อความทั้งหมดใน pack เพื่อ scan PII รอบเดียว"""
    parts = [label]
    for s in segments:
        parts.append(str(s.get("name", "")))
        parts.extend(str(t) for t in (s.get("traits") or []))
    return "\n".join(parts)


def validate_pack(label: str, segments: list[dict]) -> None:
    """ตรวจโครง + ค่า + PII — ผ่านหมดจึงเก็บ/ใช้ได้ (raise PackValidationError ถ้าไม่ผ่าน)"""
    settings = get_settings()
    if not settings.pii_detector_enabled:
        # fail-closed เหมือน ingest: detector ปิด = ไม่รับข้อมูลใหม่เข้าระบบ (กฎเหล็กข้อ 1)
        raise PackValidationError("PII detector ถูกปิดอยู่ — ปฏิเสธการสร้าง pack (GOV-01 fail-closed)")
    if not (MIN_SEGMENTS <= len(segments) <= MAX_SEGMENTS):
        raise PackValidationError(f"pack ต้องมี {MIN_SEGMENTS}-{MAX_SEGMENTS} segments")
    total_share = sum(float(s.get("share", 0)) for s in segments)
    if abs(total_share - 1.0) > 0.01:
        raise PackValidationError(f"share รวมได้ {total_share:.3f} ต้องเป็น 1.0")
    ids = [str(s.get("id", "")) for s in segments]
    if len(set(ids)) != len(ids) or any(not i for i in ids):
        raise PackValidationError("segment id ต้องมีครบและไม่ซ้ำกัน")
    for s in segments:
        if not str(s.get("name", "")).strip():
            raise PackValidationError(f"segment {s.get('id')} ไม่มีชื่อ")
        va = s.get("voice_activity")
        if not isinstance(va, (int, float)) or not 0.0 <= va <= 1.0:
            raise PackValidationError(f"voice_activity ของ {s['id']} ต้องอยู่ใน 0-1")
        priors = s.get("cultural_priors") or {}
        for k in PRIOR_KEYS:
            v = priors.get(k)
            if not isinstance(v, (int, float)) or not 0.0 <= v <= 1.0:
                raise PackValidationError(f"cultural_priors.{k} ของ {s['id']} ต้องอยู่ใน 0-1")
        mix = s.get("channel_mix") or {}
        if any(c not in VALID_CHANNELS for c in mix):
            raise PackValidationError(
                f"channel_mix ของ {s['id']} มีช่องทางที่ไม่รู้จัก (ใช้ได้: {', '.join(VALID_CHANNELS)})"
            )
        mix_total = sum(float(v) for v in mix.values())
        if abs(mix_total - 1.0) > 0.01:
            raise PackValidationError(f"channel_mix ของ {s['id']} รวมได้ {mix_total:.3f} ต้องเป็น 1.0")
    report = PIIDetector(load_allowlist()).check(_pack_text(label, segments))
    if report.blocked:
        raise PIIInPackError(report.block_reasons)


@dataclass(frozen=True)
class PersonaPack:
    id: int
    label: str
    prompt: str
    created_by: str
    created_at: str
    segments: list[dict]


class PackStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def create(self, *, label: str, segments: list[dict], prompt: str, created_by: str) -> int:
        validate_pack(label, segments)  # ด่านเดียวกันทุกทางเข้า (manual + AI)
        with self._conn() as conn:
            row = conn.execute(
                "INSERT INTO persona_packs (label, prompt, created_by, segments) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (label, prompt, created_by, json.dumps(segments, ensure_ascii=False)),
            ).fetchone()
            return int(row[0])

    def update(self, *, pack_id: int, label: str, segments: list[dict], prompt: str) -> None:
        """แก้ pack เดิม — ด่าน validate + PII เดียวกับ create (GOV-01 ทุกทางเข้า)

        ไม่แตะ created_by/created_at (provenance เดิมคงไว้ — TRUST-06)
        """
        validate_pack(label, segments)
        with self._conn() as conn:
            row = conn.execute(
                "UPDATE persona_packs SET label = %s, prompt = %s, segments = %s "
                "WHERE id = %s RETURNING id",
                (label, prompt, json.dumps(segments, ensure_ascii=False), pack_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ persona pack id {pack_id}")

    def list_packs(self) -> list[PersonaPack]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, label, prompt, created_by, created_at, segments "
                "FROM persona_packs ORDER BY created_at DESC"
            ).fetchall()
        return [
            PersonaPack(
                id=r[0],
                label=r[1],
                prompt=r[2],
                created_by=r[3],
                created_at=r[4].isoformat(),
                segments=r[5],
            )
            for r in rows
        ]

    def get(self, pack_id: int) -> PersonaPack:
        found = [p for p in self.list_packs() if p.id == pack_id]
        if not found:
            raise ValueError(f"ไม่พบ persona pack id {pack_id}")
        return found[0]

    def delete(self, pack_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM persona_packs WHERE id = %s", (pack_id,))


def factory_from_pack(pack: PersonaPack):
    """สร้าง PersonaFactory จาก pack — โครง segments ตรงกับ segments.yaml อยู่แล้ว"""
    from simulation.persona import PersonaFactory

    return PersonaFactory(segments=pack.segments)
