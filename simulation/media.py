"""สื่อกระแสหลักจำลอง (FAB-03) — สำนักข่าว agent ขยาย/กรอง narrative ตาม editorial stance

ใช้ในโลกจำลองเท่านั้น: แปลงเหตุการณ์ดิบเป็น "พาดหัวตามจุดยืนกองบรรณาธิการ" แล้ว inject
เข้า simulation เพื่อดูว่าการ frame ต่างกันเปลี่ยนปฏิกิริยาสังคมจำลองอย่างไร
— ไม่ใช่เครื่องผลิตคอนเทนต์เผยแพร่จริง (ทุก output อยู่ใต้ watermark + ป้าย simulation)
"""

import json
import re
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text

STANCES = ("amplify", "filter", "neutral")
_STANCE_TH = {
    "amplify": "ขยายประเด็น: เน้นความขัดแย้ง/ผลกระทบให้เด่น (แต่ห้ามบิดข้อเท็จจริง)",
    "filter": "กรองประเด็น: ลดทอนความร้อนแรง เน้นข้อมูลทางการ",
    "neutral": "เป็นกลาง: รายงานตามข้อเท็จจริง ไม่ใส่สี",
}


@dataclass(frozen=True)
class FramedHeadline:
    stance: str
    headline: str
    parse_ok: bool = True


def build_media_prompt(event_text: str, stance: str) -> str:
    if stance not in STANCES:
        raise ValueError(f"stance ต้องเป็นหนึ่งใน {STANCES}")
    return f"""คุณคือกองบรรณาธิการสำนักข่าว**จำลอง**ในระบบทดสอบปฏิกิริยาสังคม
จุดยืนกองบรรณาธิการ: {_STANCE_TH[stance]}

เหตุการณ์ดิบ: "{event_text}"

เขียนพาดหัวข่าว 1 พาดหัวตามจุดยืนข้างบน — ใช้ในโลกจำลองเท่านั้น ไม่ใช่คอนเทนต์เผยแพร่จริง
กติกา: ตอบภาษาไทยเท่านั้น ห้ามกุตัวเลข/ชื่อบุคคล ห้ามบิดข้อเท็จจริงในเหตุการณ์ดิบ
ตอบ JSON เท่านั้น: {{"headline": "..."}}"""


def parse_headline(stance: str, raw: str) -> FramedHeadline:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            headline = str(data.get("headline", "")).strip()
            if headline:
                return FramedHeadline(stance=stance, headline=headline)
        except json.JSONDecodeError:
            pass
    return FramedHeadline(stance=stance, headline=text[:150], parse_ok=False)


def frame_event(adapter: LLMAdapter, event_text: str, stance: str, *, seed: int) -> FramedHeadline:
    raw = adapter.chat(
        ModelTier.CROWD,
        [{"role": "user", "content": build_media_prompt(event_text, stance)}],
        max_tokens=150,
        seed=seed,
        reasoning=False,  # งานสั้น — โหมดเร็ว
    ).text
    return parse_headline(stance, raw)
