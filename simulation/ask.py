"""Conversational Querying (SIM-08) — ถามต่อจากโลกจำลอง คำตอบอ้าง reasoning trail จริง

หลัก NFR-08 (explainability): คำตอบทุกข้อต้อง cite เหตุการณ์จริงจาก trail —
analyst ได้เห็น "เฉพาะ trail ที่กรองแล้ว" เท่านั้น ห้ามตอบจากความรู้ทั่วไป
- cited_events ที่อ้างต้องมีอยู่จริง (ตรวจ index) — อ้างมั่ว = ตัดทิ้ง
- ตอบโดยไม่มี citation เลย = ติดธง "ไม่มีหลักฐานอ้างอิง" (fail-closed ไม่เชื่อคำตอบลอย)
"""

import json
import re
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text
from simulation.engine import RunResult

MAX_TRAIL_EVENTS = 80  # กัน prompt บวม — กรองก่อนส่งเสมอ


@dataclass(frozen=True)
class TrailAnswer:
    question: str
    answer: str
    cited_events: tuple[dict, ...]  # เหตุการณ์ trail จริงที่ถูกอ้าง
    grounded: bool  # False = ไม่มี citation ที่ตรวจสอบได้ — อย่าเชื่อโดยไม่ดู trail เอง


def select_trail(
    result: RunResult, *, segment: str | None = None, msg_id: str | None = None
) -> list[dict]:
    """กรอง trail ให้เหลือเฉพาะที่เกี่ยวกับคำถาม (segment/ข้อความ) — จำกัดจำนวนเสมอ"""
    seg_of = {aid: st.persona.segment_name for aid, st in result.states.items()}
    events = [
        e
        for e in result.trail
        if (segment is None or seg_of.get(e["agent"]) == segment)
        and (msg_id is None or e["msg"] == msg_id)
    ]
    return events[:MAX_TRAIL_EVENTS]


def build_ask_prompt(question: str, events: list[dict]) -> str:
    numbered = "\n".join(
        f"[{i}] round {e['round']} | agent {e['agent']} | {e['channel']} "
        f"| {e['action']} ({e['msg']})"
        for i, e in enumerate(events)
    )
    return f"""คุณคือนักวิเคราะห์ผลจำลองสังคม ตอบคำถามจาก reasoning trail ด้านล่าง **เท่านั้น**

trail (เหตุการณ์จริงจาก simulation — [เลข] คือ id สำหรับอ้างอิง):
{numbered}

คำถาม: {question}

กติกาเด็ดขาด:
- ตอบจาก trail ข้างบนเท่านั้น ห้ามใช้ความรู้ภายนอก ห้ามกุเหตุการณ์/ตัวเลข
- ทุกข้อสรุปต้องอ้าง [เลข] เหตุการณ์ที่รองรับ — ถ้า trail ไม่มีหลักฐานพอ ให้ตอบตรงๆ ว่าไม่มี
- ตอบภาษาไทยเท่านั้น ตอบ JSON เท่านั้น:
{{"answer": "คำตอบ (มี [เลข] อ้างอิงในเนื้อหา)", "cited_events": [0, 5]}}"""


def parse_answer(question: str, raw: str, events: list[dict]) -> TrailAnswer:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    answer, cited_idx = text[:500], []
    if m:
        try:
            data = json.loads(m.group(0))
            answer = str(data.get("answer", "")).strip() or text[:500]
            cited_idx = [
                int(i)
                for i in data.get("cited_events", [])
                if isinstance(i, int | float) and 0 <= int(i) < len(events)  # อ้างมั่ว = ตัดทิ้ง
            ]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    cited = tuple(events[i] for i in cited_idx)
    return TrailAnswer(
        question=question, answer=answer, cited_events=cited, grounded=len(cited) > 0
    )


def ask_world(
    adapter: LLMAdapter,
    result: RunResult,
    question: str,
    *,
    segment: str | None = None,
    msg_id: str | None = None,
    seed: int = 0,
) -> TrailAnswer:
    events = select_trail(result, segment=segment, msg_id=msg_id)
    if not events:
        return TrailAnswer(
            question=question,
            answer="trail ไม่มีเหตุการณ์ที่เข้าเงื่อนไขคำถามนี้ — ไม่มีหลักฐานให้วิเคราะห์",
            cited_events=(),
            grounded=False,
        )
    raw = adapter.chat(
        ModelTier.ANALYST,
        [{"role": "user", "content": build_ask_prompt(question, events)}],
        max_tokens=500,
        temperature=0.0,
        seed=seed,
    ).text
    return parse_answer(question, raw, events)


def render_answer(ta: TrailAnswer) -> str:
    lines = [f"**ถาม:** {ta.question}", "", f"**ตอบ:** {ta.answer}", ""]
    if ta.grounded:
        lines.append("หลักฐานจาก trail:")
        lines += [
            f"- round {e['round']} | {e['agent']} | {e['channel']} | {e['action']}"
            for e in ta.cited_events
        ]
    else:
        lines.append("⚠️ **ไม่มีหลักฐานอ้างอิงจาก trail ที่ตรวจสอบได้ — อย่าใช้คำตอบนี้ตัดสินใจ**")
    return "\n".join(lines)
