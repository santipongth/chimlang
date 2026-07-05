"""Entity name normalization — รวมชื่อพ้องให้เป็น node เดียว (คุณภาพ graph)

ปัญหาที่พบจาก ingest จริงรอบแรก: "กทม." / "กรุงเทพมหานคร" / "กรุงเทพฯ" ถูกสร้าง
เป็นคนละ node ทำให้ indirect query พลาด — แก้ด้วย alias map ที่ commit ผ่าน git
(เพิ่ม alias ใหม่เมื่อเจอจากการตรวจ graph ไม่เดาล่วงหน้า)
"""

import re

from graphlayer.extraction import Entity, Extraction, Relation

# alias -> canonical (เฉพาะที่ยืนยันจาก graph จริงแล้วว่าซ้ำ)
ALIASES: dict[str, str] = {
    "กรุงเทพมหานคร": "กทม.",
    "กรุงเทพฯ": "กทม.",
    "กรุงเทพ": "กทม.",
    "คณะทำงานนโยบายจราจร กทม.": "คณะทำงานนโยบายจราจร",
    "คณะทำงานด้านจราจร": "คณะทำงานนโยบายจราจร",
}


def canonical_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    return ALIASES.get(cleaned, cleaned)


def normalize_extraction(ex: Extraction) -> Extraction:
    entities: dict[str, Entity] = {}
    for e in ex.entities:
        name = canonical_name(e.name)
        entities.setdefault(name, Entity(name=name, type=e.type))
    relations = tuple(
        Relation(
            source=canonical_name(r.source),
            relation=r.relation,
            target=canonical_name(r.target),
            evidence=r.evidence,
        )
        for r in ex.relations
        # ตัด self-loop ที่เกิดจากการ merge ชื่อพ้อง
        if canonical_name(r.source) != canonical_name(r.target)
    )
    return Extraction(entities=tuple(entities.values()), relations=relations)
