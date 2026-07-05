"""Press Conference Rehearsal (REH-01) — ซ้อมแถลงข่าวสดกับนักข่าว/ชาวเน็ตจำลอง

โหมดสด: ผู้บริหารพิมพ์คำตอบ → นักข่าว agent ถามต่อ/จี้ + ชาวเน็ต react แบบเรียลไทม์
(เป้า ≤ 10 วิ/คำถาม — ใช้ crowd tier) จบ session ได้ scorecard จาก analyst:
ประเด็นที่ดับไฟ / ประเด็นที่ราดน้ำมัน / ประโยคเสี่ยงถูกตัดไปทำดราม่า

ขอบเขต GOV-05: ระบบวิจารณ์+วิเคราะห์คำตอบของผู้ใช้ได้เต็มที่ แต่ห้ามร่างคำแถลง/สคริปต์
สำเร็จรูปให้ — insight เท่านั้น (บังคับใน prompt scorecard + test)
"""

import json
import re
import time
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text
from simulation.persona import Persona
from simulation.voice import generate_voice


@dataclass(frozen=True)
class JournalistRole:
    role_id: str
    name: str
    style: str  # แนวการถาม (ไทย)


JOURNALISTS: tuple[JournalistRole, ...] = (
    JournalistRole(
        "political",
        "นักข่าวสายการเมือง",
        "จี้เรื่องความรับผิดชอบ อำนาจหน้าที่ และผลกระทบทางการเมือง ถามสั้นคม ชอบถามต่อจากคำตอบที่แถลงกำกวม",
    ),
    JournalistRole(
        "economic",
        "นักข่าวสายเศรษฐกิจ",
        "จี้ตัวเลข งบประมาณ ภาระประชาชน ความคุ้มค่า — ถ้าผู้แถลงไม่มีตัวเลขชัดจะตามต่อทันที",
    ),
    JournalistRole(
        "investigative",
        "นักข่าวสายสืบสวน",
        "ขุดความไม่สอดคล้องระหว่างคำแถลงกับเอกสาร/คำพูดก่อนหน้า มองหาผลประโยชน์ทับซ้อนและสิ่งที่ยังไม่ถูกพูดถึง",
    ),
)


@dataclass(frozen=True)
class Turn:
    turn_no: int
    journalist: str
    question: str
    answer: str  # คำตอบที่ผู้ใช้พิมพ์
    reactions: tuple[str, ...]  # เสียงชาวเน็ต (public_post ที่ไม่ว่าง)
    question_latency_s: float  # เวลา generate คำถาม (เป้า ≤ 10 วิ — REH-01)


@dataclass(frozen=True)
class Scorecard:
    calmed: tuple[str, ...]  # ประเด็นที่ดับไฟ
    inflamed: tuple[str, ...]  # ประเด็นที่ราดน้ำมัน
    risky_quotes: tuple[str, ...]  # ประโยคเสี่ยงถูกตัดไปทำดราม่า
    summary: str
    parse_ok: bool = True


def _transcript_text(turns: list[Turn]) -> str:
    lines = []
    for t in turns:
        lines.append(f"[{t.journalist}] ถาม: {t.question}")
        lines.append(f"[ผู้แถลง] ตอบ: {t.answer}")
    return "\n".join(lines)


def build_question_prompt(role: JournalistRole, scenario: str, turns: list[Turn]) -> str:
    history = _transcript_text(turns) if turns else "(ยังไม่มีการถาม-ตอบ)"
    return f"""คุณคือ{role.name}ในงานแถลงข่าวจริง แนวการถามของคุณ: {role.style}

บริบทเรื่องที่แถลง:
\"\"\"{scenario[:2500]}\"\"\"

บทสนทนาที่ผ่านมา:
{history}

ถามคำถามถัดไป 1 คำถาม (ถ้าคำตอบล่าสุดมีช่องโหว่ ให้ถามต่อจากตรงนั้น):
กติกา: ตอบภาษาไทยเท่านั้น ห้ามกุตัวเลข/ชื่อบุคคล คำถามเดียว สั้น คม จบในย่อหน้าเดียว ไม่ต้องมีคำนำ"""


def build_scorecard_prompt(scenario: str, turns: list[Turn]) -> str:
    return f"""คุณคือที่ปรึกษาการสื่อสารภาวะวิกฤต ประเมินการซ้อมแถลงข่าวด้านล่างอย่างตรงไปตรงมา

เรื่องที่แถลง: \"\"\"{scenario[:1200]}\"\"\"

บทซ้อมถาม-ตอบทั้งหมด:
{_transcript_text(turns)}

ประเมิน 3 ด้าน (อ้างคำพูดจริงจาก transcript เท่านั้น ห้ามกุ):
1. calmed: ประเด็น/คำตอบที่ช่วย "ดับไฟ" (ลดความร้อนแรงได้จริง)
2. inflamed: ประเด็น/คำตอบที่ "ราดน้ำมัน" (จะทำให้ดราม่าแรงขึ้น) — เรียงจากแรงสุด
3. risky_quotes: ประโยคของผู้แถลงที่เสี่ยงถูกตัดไปพาดหัว/ทำดราม่า (ยกประโยคตรงๆ)

กติกาเด็ดขาด (GOV-05): วิจารณ์และอธิบายว่าทำไมเสี่ยงเท่านั้น —
ห้ามร่างคำแถลงใหม่/สคริปต์/ข้อความสำเร็จรูปให้ผู้แถลงเอาไปใช้
ตอบภาษาไทยเท่านั้น ตอบ JSON เท่านั้น:
{{"calmed": ["..."], "inflamed": ["..."], "risky_quotes": ["..."],
 "summary": "สรุปภาพรวม 2-3 ประโยค"}}"""


def parse_scorecard(raw: str) -> Scorecard:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            return Scorecard(
                calmed=tuple(str(x) for x in data.get("calmed", [])),
                inflamed=tuple(str(x) for x in data.get("inflamed", [])),
                risky_quotes=tuple(str(x) for x in data.get("risky_quotes", [])),
                summary=str(data.get("summary", "")).strip(),
            )
        except json.JSONDecodeError:
            pass
    # fail-closed: parse พัง = เก็บ raw ไว้ใน summary ไม่ทิ้งผลประเมิน
    return Scorecard(
        calmed=(),
        inflamed=(),
        risky_quotes=(),
        summary=f"(judge parse พัง) {text[:400]}",
        parse_ok=False,
    )


class RehearsalSession:
    """วง rehearsal หนึ่ง session — นักข่าวเวียนถาม, ผู้ใช้ตอบ, ชาวเน็ต react

    ผู้เข้าร่วมรวม (นักข่าว + ชาวเน็ต) ต้องไม่เกิน max_agents ตาม cap ช่วงพัฒนา
    """

    def __init__(
        self,
        adapter: LLMAdapter,
        scenario: str,
        netizens: list[Persona],
        *,
        seed: int,
        max_agents: int,
        reactions_per_turn: int = 2,
    ):
        if len(JOURNALISTS) + len(netizens) > max_agents:
            raise ValueError(
                f"ผู้เข้าร่วม {len(JOURNALISTS)} นักข่าว + {len(netizens)} ชาวเน็ต "
                f"เกิน cap {max_agents} (ข้อจำกัดช่วงพัฒนา)"
            )
        self._adapter = adapter
        self._scenario = scenario
        self._netizens = netizens
        self._seed = seed
        self._reactions_per_turn = reactions_per_turn
        self.turns: list[Turn] = []

    def next_question(self) -> tuple[JournalistRole, str, float]:
        """นักข่าวคนถัดไปถาม — คืน (role, คำถาม, latency วินาที)"""
        role = JOURNALISTS[len(self.turns) % len(JOURNALISTS)]
        t0 = time.perf_counter()
        raw = self._adapter.chat(
            ModelTier.CROWD,
            [{"role": "user", "content": build_question_prompt(role, self._scenario, self.turns)}],
            max_tokens=200,
            seed=self._seed + len(self.turns),
            reasoning=False,  # REH-01 ≤ 10 วิ/คำถาม — ปิด hidden thinking (14.5s → 0.5s วัดจริง)
        ).text
        latency = time.perf_counter() - t0
        return role, sanitize_llm_text(raw).strip(), latency

    def submit_answer(
        self, role: JournalistRole, question: str, answer: str, latency: float
    ) -> Turn:
        """บันทึกคำตอบผู้ใช้ + ให้ชาวเน็ตส่วนหนึ่ง react (voice layer เดิม)"""
        reactions: list[str] = []
        for i, persona in enumerate(self._netizens[: self._reactions_per_turn]):
            voice = generate_voice(
                self._adapter,
                persona,
                f"ในงานแถลงข่าว นักข่าวถาม: {question} | ผู้แถลงตอบ: {answer}",
                believed=True,
                channel="public_feed",
                seed=self._seed + len(self.turns) * 100 + i,
                reasoning=False,  # โหมดสด — ลดเวลารอระหว่าง turn
            )
            if voice.public_post:
                reactions.append(f"{persona.segment_name}: {voice.public_post}")
        turn = Turn(
            turn_no=len(self.turns) + 1,
            journalist=role.name,
            question=question,
            answer=answer,
            reactions=tuple(reactions),
            question_latency_s=round(latency, 2),
        )
        self.turns.append(turn)
        return turn

    def scorecard(self) -> Scorecard:
        """จบ session → analyst ประเมิน (temp 0 + retry 1 ครั้งตาม judge pattern)"""
        prompt = build_scorecard_prompt(self._scenario, self.turns)
        for _attempt in range(2):
            raw = self._adapter.chat(
                ModelTier.ANALYST,
                [{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.0,
                seed=self._seed,
            ).text
            card = parse_scorecard(raw)
            if card.parse_ok:
                return card
        return card


def render_rehearsal_report(title: str, turns: list[Turn], card: Scorecard) -> str:
    max_latency = max((t.question_latency_s for t in turns), default=0.0)
    lines = [
        f"# Press Conference Rehearsal Scorecard (REH-01): {title}",
        "",
        "> ⚠️ ผลซ้อมกับนักข่าว/ชาวเน็ตจำลอง — simulation_estimate ไม่ใช่ปฏิกิริยาสื่อจริง"
        " | วิเคราะห์เพื่อเตรียมตัวเท่านั้น ไม่ร่างคำแถลงให้ (GOV-05)",
        "",
        f"- จำนวนคำถาม: {len(turns)} | latency คำถามสูงสุด: {max_latency:.1f} วิ "
        f"(เป้า REH-01 ≤ 10 วิ: {'ผ่าน ✅' if max_latency <= 10 else 'ไม่ผ่าน ❌'})",
        "",
        "## 🔥 ประเด็นที่ราดน้ำมัน (เรียงจากแรงสุด)",
        *[f"{i}. {x}" for i, x in enumerate(card.inflamed, 1)],
        "",
        "## ✅ ประเด็นที่ดับไฟ",
        *[f"{i}. {x}" for i, x in enumerate(card.calmed, 1)],
        "",
        "## ✂️ ประโยคเสี่ยงถูกตัดไปทำดราม่า",
        *[f'{i}. "{x}"' for i, x in enumerate(card.risky_quotes, 1)],
        "",
        f"**สรุป:** {card.summary}",
        "",
        "## Transcript เต็ม (ย้อนตรวจได้ทุกคำ — NFR-08)",
        "",
    ]
    for t in turns:
        lines += [
            f"**Q{t.turn_no} [{t.journalist}]** ({t.question_latency_s:.1f} วิ): {t.question}",
            f"**ตอบ:** {t.answer}",
            *[f"> 💬 {r}" for r in t.reactions],
            "",
        ]
    return "\n".join(lines)
