"""Persona Provenance Card (TRUST-06) — ทุก segment ต้องมีบัตรแสดงที่มาของข้อมูล

หลัก Provenance everywhere: ผู้อ่านรายงานต้องรู้ว่า persona ถูกสร้างจากอะไร เมื่อไหร่
ถ่วงน้ำหนักอย่างไร และมี bias อะไรที่รู้อยู่แล้ว — โดยเฉพาะช่วงที่ยังใช้ข้อมูลสังเคราะห์
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from simulation.persona import DEFAULT_SEGMENTS_PATH


@dataclass(frozen=True)
class ProvenanceCard:
    segment_id: str
    segment_name: str
    share: float
    data_source: str
    data_date: str
    weighting_method: str
    known_bias: tuple[str, ...]
    coverage: str


def build_cards(segments_path: Path | str = DEFAULT_SEGMENTS_PATH) -> list[ProvenanceCard]:
    raw = yaml.safe_load(Path(segments_path).read_text(encoding="utf-8"))
    prov = (raw.get("meta") or {}).get("provenance")
    if not prov:
        raise ValueError(
            "segments.yaml ไม่มี meta.provenance — TRUST-06 บังคับ: persona ทุก segment ต้องมีที่มา"
        )
    return [
        ProvenanceCard(
            segment_id=s["id"],
            segment_name=s["name"],
            share=s["share"],
            data_source=prov["data_source"],
            data_date=prov["data_date"],
            weighting_method=prov["weighting_method"],
            known_bias=tuple(prov.get("known_bias") or ()),
            coverage=prov["coverage"],
        )
        for s in raw["segments"]
    ]


def render_provenance_section(cards: list[ProvenanceCard]) -> str:
    first = cards[0]
    lines = [
        "## Persona Provenance (TRUST-06): persona ชุดนี้มาจากไหน",
        "",
        f"- แหล่งข้อมูล: {first.data_source} (ณ {first.data_date})",
        f"- วิธีถ่วงน้ำหนัก: {first.weighting_method}",
        f"- ระดับความครอบคลุม: {first.coverage}",
        "- **bias ที่ทราบ (อ่านก่อนใช้ผล):**",
    ]
    lines += [f"  - {b}" for b in first.known_bias]
    lines += [
        "",
        "| segment | share ที่ตั้งไว้ |",
        "|---|---|",
    ]
    lines += [f"| {c.segment_name} | {c.share:.0%} |" for c in cards]
    return "\n".join(lines)
