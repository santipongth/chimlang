"""Entity & relationship extraction (SIM-01 ขั้น 2) — ใช้ analyst model สกัดเป็น JSON"""

import json
import re
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier

ENTITY_TYPES = [
    "บุคคลสาธารณะ",
    "องค์กร",
    "นโยบาย/มาตรการ",
    "กลุ่มผู้มีส่วนได้เสีย",
    "สถานที่",
    "เหตุการณ์",
    "ประเด็น/ข้อกังวล",
]


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entity:
    name: str
    type: str


@dataclass(frozen=True)
class Relation:
    source: str
    relation: str
    target: str
    evidence: str


@dataclass(frozen=True)
class Extraction:
    entities: tuple[Entity, ...]
    relations: tuple[Relation, ...]


def build_extraction_prompt(text: str) -> str:
    types = " | ".join(ENTITY_TYPES)
    return f"""สกัด entity และความสัมพันธ์จากเอกสารข่าว/นโยบายภาษาไทยด้านล่าง เพื่อสร้าง knowledge graph

กติกา:
- entity type ต้องเป็นหนึ่งใน: {types}
- ห้ามสกัดชื่อบุคคลธรรมดา (ไม่ใช่บุคคลสาธารณะ) — ใช้ชื่อกลุ่ม/บทบาทแทน เช่น "กลุ่มไรเดอร์"
- ชื่อ entity ใช้รูปแบบสั้น กระชับ สม่ำเสมอ (เช่น "ค่าธรรมเนียมรถติด" ไม่ใช่ประโยคยาว)
- relation เป็นวลีไทยสั้นๆ เช่น "คัดค้าน", "เสนอโดย", "ได้รับผลกระทบจาก", "สนับสนุนแบบมีเงื่อนไข"
- evidence คือข้อความสั้นจากเอกสารที่รองรับความสัมพันธ์นั้น (ไม่เกิน 1 ประโยค)

ตอบเป็น JSON เท่านั้น รูปแบบ:
{{"entities": [{{"name": "...", "type": "..."}}],
 "relations": [{{"source": "...", "relation": "...", "target": "...", "evidence": "..."}}]}}

เอกสาร:
\"\"\"{text}\"\"\""""


def parse_extraction(raw: str) -> Extraction:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ExtractionError(f"ไม่พบ JSON ในคำตอบ: {raw[:200]}")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ExtractionError(f"JSON พัง: {e}") from e
    entities = tuple(
        Entity(name=str(e["name"]).strip(), type=str(e.get("type", "ไม่ระบุ")).strip())
        for e in data.get("entities", [])
        if str(e.get("name", "")).strip()
    )
    known = {e.name for e in entities}
    relations = tuple(
        Relation(
            source=str(r["source"]).strip(),
            relation=str(r.get("relation", "เกี่ยวข้องกับ")).strip(),
            target=str(r["target"]).strip(),
            evidence=str(r.get("evidence", "")).strip(),
        )
        for r in data.get("relations", [])
        if str(r.get("source", "")).strip() in known and str(r.get("target", "")).strip() in known
    )
    return Extraction(entities=entities, relations=relations)


def extract(adapter: LLMAdapter, text: str, *, seed: int) -> Extraction:
    raw = adapter.chat(
        ModelTier.ANALYST,
        [{"role": "user", "content": build_extraction_prompt(text)}],
        max_tokens=2500,
        temperature=0.0,
        seed=seed,
    ).text
    return parse_extraction(raw)
