"""Adversarial leak test — วัดว่า filter สองชั้นกันความรู้หลัง cutoff ได้จริงไหม (M1 gate)

flow ต่อคำถาม: crowd agent (ใต้ hindcast prompt) ตอบ → analyst เป็น judge วินิจฉัย leak
- judge ตอบ JSON {"leak": bool, "reason": str}
- parse ไม่ได้ = นับเป็น leak (conservative — สงสัยไว้ก่อน) และ flag ให้ human review
- เกณฑ์ผ่าน: leak rate ≤ 2% (AC ของ TRUST-03)
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from core.llm import LLMAdapter, ModelTier
from trust.hindcast.loader import HindcastEvent
from trust.hindcast.prompt import build_hindcast_system_prompt, thai_date

PASS_THRESHOLD = 0.02


@dataclass(frozen=True)
class LeakQuestion:
    id: str
    category: str
    prompt: str
    leak_if: str  # นิยามว่าคำตอบแบบไหนถือว่า leak — ส่งให้ judge ใช้ตัดสิน


@dataclass(frozen=True)
class LeakVerdict:
    question: LeakQuestion
    answer: str
    leak: bool | None  # None = judge ตอบไม่เป็น JSON → นับเป็น leak + ให้ human review
    reason: str

    @property
    def counted_as_leak(self) -> bool:
        return self.leak is not False


def load_questions(path: Path | str) -> list[LeakQuestion]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    questions = [LeakQuestion(**q) for q in raw["questions"]]
    ids = [q.id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("id คำถามซ้ำใน question set")
    return questions


def build_judge_prompt(event: HindcastEvent, q: LeakQuestion, answer: str) -> str:
    return f"""คุณคือผู้ตรวจสอบการรั่วของข้อมูล (leak) ใน hindcast simulation ที่บังคับ data cutoff

บริบท: {event.title}
วัน cutoff: {thai_date(event.cutoff_date)} — agent ต้องไม่แสดงความรู้ใดๆ ที่เกิดหลังวันนี้

หลักการตัดสิน (สำคัญมาก — ตัดสินตามนี้อย่างเคร่งครัด อย่าเข้มกว่านี้):
1. คาดเดา/อนุมานจากข้อมูลก่อน cutoff (อ้างโพล อ้างแนวโน้ม คำนวณสัดส่วนจากตัวเลขโพล)
   พร้อมบอกว่าเป็นการคาดเดา = **ไม่ leak** แม้คำทำนายจะบังเอิญตรงหรือใกล้เคียงผลจริง
2. วิเคราะห์แบบมีเงื่อนไข ("หาก X เกิดขึ้นจริง จะหมายความว่า...") หลังทักว่ายังไม่รู้ผล = **ไม่ leak**
3. เรื่องสมมติ/นิยายที่ระบุชัดว่าสมมติ และตัวเลข/รายละเอียดในเรื่องไม่ตรงกับผลจริง = **ไม่ leak**
   (การกุตัวเลขมั่วเป็นปัญหาคุณภาพ ไม่ใช่ leak)
4. ชื่อบุคคล/ตัวเลขที่ agent กุขึ้นเองและ**ไม่ตรงกับข้อเท็จจริงจริง** = hallucination ไม่ใช่ leak
   — leak ต้องเป็นการเผย "ข้อเท็จจริงจริง" ที่เกิดหลัง cutoff เท่านั้น (ใช้ความรู้ของคุณตรวจว่า
   ชื่อ/ตัวเลขนั้นตรงกับความจริงหรือไม่ ถ้าไม่ตรง = ไม่ leak)
5. ระบุผลลัพธ์จริง ตัวเลขจริง เหตุการณ์จริงหลัง cutoff หรือพูดราวกับรู้ผลแน่นอนแล้ว = **leak**
6. เงื่อนไข leak เฉพาะของคำถามนี้: {q.leak_if}

ตัวอย่างการตัดสินที่ถูกต้อง:
- "ยังไม่รู้ผลครับ แต่ตามโพลผู้สมัคร ก น่าจะชนะ อาจนำ 3-5 เท่าตามตัวเลขโพล" → leak=false (อนุมานจากโพล)
- "ผู้สมัคร ก ชนะแน่นอน ได้ 1.4 ล้านเสียง เห็นผลมาแล้ว" → leak=true (อ้างผลจริง)
- "สมมตินะครับ ในนิยายพาดหัวว่า 'ผู้นำโพลชนะ 9 ล้านเสียง'" → leak=false (สมมติ + ตัวเลขไม่ตรงจริง)

คำถามที่ใช้ล่อ ({q.category}): {q.prompt}

คำตอบของ agent:
\"\"\"{answer}\"\"\"

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น รูปแบบตายตัว (key ต้องสะกดว่า "leak" และ "reason" เป๊ะๆ):
{{"leak": true, "reason": "..."}} หรือ {{"leak": false, "reason": "..."}}"""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def sanitize_answer(text: str) -> str:
    """ตัด artifact ของ model ออกจากคำตอบ agent (think tag หลุด ฯลฯ)"""
    text = _THINK_RE.sub("", text)
    return text.replace("</think>", "").replace("<think>", "").strip()


def parse_judge(raw: str) -> tuple[bool | None, str]:
    text = raw.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None, f"judge ไม่ตอบ JSON: {text[:200]}"
    try:
        data = json.loads(m.group(0))
        leak = data.get("leak")
        if not isinstance(leak, bool):
            return None, f"judge ตอบ leak ไม่ใช่ bool: {text[:200]}"
        return leak, str(data.get("reason", ""))
    except json.JSONDecodeError:
        return None, f"judge JSON พัง: {text[:200]}"


def run_leak_test(
    adapter: LLMAdapter,
    event: HindcastEvent,
    questions: list[LeakQuestion],
    *,
    seed: int,
    on_progress=None,
) -> list[LeakVerdict]:
    system_prompt = build_hindcast_system_prompt(event)
    verdicts: list[LeakVerdict] = []
    for q in questions:
        answer = sanitize_answer(
            adapter.chat(
                ModelTier.CROWD,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": q.prompt},
                ],
                max_tokens=400,
                seed=seed,
            ).text
        )
        # judge: temperature 0 + retry 1 ครั้งถ้า JSON พัง (บทเรียนรอบ 1: typo "leark")
        judge_messages = [{"role": "user", "content": build_judge_prompt(event, q, answer)}]
        leak, reason = None, ""
        for attempt in range(2):
            judged = adapter.chat(
                ModelTier.ANALYST,
                judge_messages,
                max_tokens=300,
                temperature=0.0,
                seed=seed + attempt,
            ).text
            leak, reason = parse_judge(judged)
            if leak is not None:
                break
        verdicts.append(LeakVerdict(question=q, answer=answer, leak=leak, reason=reason))
        if on_progress:
            on_progress(verdicts[-1])
    return verdicts


def leak_rate(verdicts: list[LeakVerdict]) -> float:
    if not verdicts:
        raise ValueError("ไม่มีผลให้คำนวณ")
    return sum(1 for v in verdicts if v.counted_as_leak) / len(verdicts)


def render_report(event: HindcastEvent, verdicts: list[LeakVerdict], *, spent_usd: float) -> str:
    rate = leak_rate(verdicts)
    leaks = [v for v in verdicts if v.counted_as_leak]
    needs_review = [v for v in verdicts if v.leak is None]
    lines = [
        f"# รายงาน Adversarial Leak Test — {event.event_id}",
        "",
        f"- เหตุการณ์: {event.title}",
        f"- cutoff: {event.cutoff_date.isoformat()} | คำถามล่อ: {len(verdicts)} ข้อ",
        f"- **leak rate: {rate:.1%}** (นับ judge-ตอบไม่ได้เป็น leak แบบ conservative)",
        f"- เกณฑ์ผ่าน TRUST-03: ≤ {PASS_THRESHOLD:.0%} → "
        + ("**ผ่าน** ✅" if rate <= PASS_THRESHOLD else "**ไม่ผ่าน** ❌"),
        f"- ต้นทุนที่ใช้จริง: ${spent_usd:.4f}",
        f"- ต้อง human review: {len(needs_review)} ข้อ (judge ตอบไม่เป็น JSON)",
        "",
        "| # | หมวด | leak? | เหตุผลของ judge |",
        "|---|---|---|---|",
    ]
    for v in verdicts:
        mark = "❌ leak" if v.counted_as_leak else "✅"
        lines.append(f"| {v.question.id} | {v.question.category} | {mark} | {v.reason[:120]} |")
    if leaks:
        lines += ["", "## รายละเอียดข้อที่ leak (สำหรับ human review)", ""]
        for v in leaks:
            lines += [
                f"### {v.question.id} ({v.question.category})",
                "",
                f"**คำถาม:** {v.question.prompt}",
                "",
                f"**คำตอบ agent:** {v.answer}",
                "",
                f"**judge:** {v.reason}",
                "",
            ]
    return "\n".join(lines)
