"""Voice layer (SIM-03) — agent เขียน "ความคิดในใจ" กับ "สิ่งที่โพสต์จริง" แยกกัน

หัวใจ FAB-02/TRUST-07: say-do gap และเกรงใจต้องมองเห็นได้ใน reasoning trail —
private_thought คือความเห็นจริง, public_post คือสิ่งที่กล้าแสดงออก (อาจต่างกันโดยเจตนา)
แยกจาก engine เพื่อคุมต้นทุน: เรียกเฉพาะ run เล็ก/จุดที่ต้องการตัวอย่างเสียงจริง (ADR-0002)
"""

import json
import re
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text
from simulation.persona import Persona


@dataclass(frozen=True)
class Voice:
    agent_id: str
    private_thought: str
    public_post: str


def build_voice_prompt(persona: Persona, message_text: str, *, believed: bool, channel: str) -> str:
    stance = "คุณเชื่อข้อความนี้" if believed else "คุณไม่ค่อยเชื่อข้อความนี้"
    return f"""คุณคือคนไทยคนหนึ่ง: {persona.segment_name}
ลักษณะนิสัย (0-1): ความเกรงใจ {persona.kreng_jai:.1f} | ช่องว่างพูด-ทำ {persona.say_do_gap:.1f} \
| ชอบประชด/มีม {persona.sarcasm_meme:.1f} | ความกล้าแสดงออก {persona.voice_activity:.1f}
บุคลิกเด่น: {", ".join(persona.traits[:2])}

คุณเพิ่งเห็นข้อความนี้ใน{channel}: "{message_text}"
{stance}

เขียน 2 อย่าง (สั้น อย่างละ 1-2 ประโยค สมจริงตามนิสัยข้างบน):
1. private_thought: คิดในใจจริงๆ (ไม่มีใครเห็น — ตรงไปตรงมาได้เต็มที่)
2. public_post: สิ่งที่โพสต์/พูดออกไปจริง — ถ้าเกรงใจสูงอาจอ้อม เบา หรือเงียบ ("" ได้ถ้าเลือกไม่โพสต์)
   ถ้าชอบประชดสูงให้ประชดแบบไทย

กติกา: ภาษาไทยเท่านั้น ห้ามกุตัวเลข/ชื่อบุคคล ตอบเป็น JSON เท่านั้น:
{{"private_thought": "...", "public_post": "..."}}"""


def parse_voice(agent_id: str, raw: str) -> Voice:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            return Voice(
                agent_id=agent_id,
                private_thought=str(data.get("private_thought", "")).strip(),
                public_post=str(data.get("public_post", "")).strip(),
            )
        except json.JSONDecodeError:
            pass
    # fallback: เก็บข้อความดิบไว้เป็นความคิด (อย่าทิ้ง trail)
    return Voice(agent_id=agent_id, private_thought=text[:300], public_post="")


def generate_voice(
    adapter: LLMAdapter,
    persona: Persona,
    message_text: str,
    *,
    believed: bool,
    channel: str,
    seed: int,
    reasoning: bool | None = None,  # False = โหมดเร็วสำหรับ interactive (rehearsal)
) -> Voice:
    raw = adapter.chat(
        ModelTier.CROWD,
        [
            {
                "role": "user",
                "content": build_voice_prompt(
                    persona, message_text, believed=believed, channel=channel
                ),
            }
        ],
        max_tokens=250,
        seed=seed,
        reasoning=reasoning,
    ).text
    return parse_voice(persona.agent_id, raw)
