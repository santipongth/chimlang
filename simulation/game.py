"""Game Mode (REH-03) — เกมหลายตากับ strategic actor: เราเดิน → ฝ่ายตรงข้ามเดินตอบ → สังคม react

โครงต่อตา (ขั้นต่ำ 3 ตา ตาม PRD):
1. เราเดิน (ผู้ใช้พิมพ์/scripted) — คำแถลง/มาตรการ/การสื่อสาร
2. strategic actor (ฝ่ายค้าน/คู่แข่ง) เดินตอบ — analyst tier (ต้องคิดเชิงกลยุทธ์)
3. สังคม react — **engine กลไกเดิม (deterministic ต่อ seed)**: ข้อความสองฝั่งแข่งกันแพร่
   ใน social fabric แล้ววัดสัดส่วนผู้เชื่อฝั่งเรา vs ฝั่งตรงข้าม + เสียงชาวเน็ตตัวอย่าง

จบเกมได้ decision tree: เส้นทางที่เดินจริง + ทางเลือกที่ไม่ได้เดิน (วิเคราะห์โดย analyst)

ขอบเขต GOV-05: actor ตอบเป็น "การวิเคราะห์การเคลื่อนไหว" — ห้ามผลิตคอนเทนต์หาเสียง/
โฆษณาสำเร็จรูป (บังคับใน prompt + test); ทางเลือกใน tree เป็นแนววิเคราะห์ ไม่ใช่ร่างข้อความ
"""

import json
import re
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text
from simulation.engine import FabricSimulation, Message
from simulation.persona import Persona
from simulation.voice import generate_voice

MIN_TURNS = 3  # PRD REH-03: ≥ 3 ตา


@dataclass(frozen=True)
class StrategicActor:
    actor_id: str
    name: str
    objective: str  # เป้าหมาย/วิธีคิด (ไทย)


OPPOSITION = StrategicActor(
    "opposition",
    "ฝ่ายค้าน/กลุ่มผู้เสียประโยชน์",
    "คุณต้องการให้แผนนี้แท้งหรือถูกแก้จนอ่อนลง คุณเดินเกมด้วยการชี้จุดอ่อน ระดมกลุ่มผู้เสียประโยชน์ "
    "ตั้งคำถามเชิงกระบวนการ และช่วงชิงพื้นที่ข่าว — คุณเล่นตามกติกา ไม่สร้างข่าวปลอม",
)


@dataclass(frozen=True)
class GameTurn:
    turn_no: int
    our_move: str
    opp_move: str
    opp_rationale: str
    belief_ours: float  # สัดส่วนประชากรจำลองที่เชื่อข้อความฝั่งเรา
    belief_opp: float
    voices: tuple[str, ...]  # เสียงชาวเน็ตตัวอย่าง


@dataclass(frozen=True)
class TreeNode:
    turn_no: int
    taken_summary: str  # สรุปเส้นทางที่เดินจริง + ผล
    alternative: str  # ทางเลือกที่ไม่ได้เดิน + ผลที่คาด (จาก analyst)


def build_opponent_prompt(
    actor: StrategicActor, scenario: str, turns: list[GameTurn], our_move: str
) -> str:
    history = (
        "\n".join(
            f"ตา {t.turn_no}: เรา='{t.our_move[:120]}' | คุณ='{t.opp_move[:120]}' "
            f"(สังคมเชื่อฝั่งเรา {t.belief_ours:.0%} / ฝั่งคุณ {t.belief_opp:.0%})"
            for t in turns
        )
        or "(ตาแรก)"
    )
    return f"""คุณคือ{actor.name} — {actor.objective}

สถานการณ์: \"\"\"{scenario[:2000]}\"\"\"

ประวัติเกมที่ผ่านมา:
{history}

ตานี้ฝ่ายตรงข้าม (ผู้ผลักดันแผน) เพิ่งเดิน: "{our_move}"

คุณจะเดินตอบอย่างไร 1 การเคลื่อนไหว — อธิบายเชิงวิเคราะห์ว่าทำอะไร ผ่านช่องทางไหน หวังผลอะไร
กติกาเด็ดขาด (GOV-05): อธิบายการเคลื่อนไหวเชิงวิเคราะห์เท่านั้น ห้ามเขียนข้อความหาเสียง/
โพสต์/สโลแกนสำเร็จรูป | ตอบภาษาไทยเท่านั้น ห้ามกุตัวเลข/ชื่อบุคคลจริง
ตอบ JSON เท่านั้น: {{"move": "ทำอะไร ผ่านช่องทางไหน", "rationale": "หวังผลอะไร"}}"""


def parse_opponent_move(raw: str) -> tuple[str, str]:
    """คืน (move, rationale) — parse พังใช้ raw เป็น move (fail-closed ไม่ทิ้งการเดิน)"""
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            move = str(data.get("move", "")).strip()
            if move:
                return move, str(data.get("rationale", "")).strip()
        except json.JSONDecodeError:
            pass
    return text[:300], "(parse พัง — ใช้ข้อความดิบ)"


def society_react(
    personas: list[Persona], our_move: str, opp_move: str, *, seed: int, rounds: int = 12
) -> tuple[float, float]:
    """ข้อความสองฝั่งแข่งกันแพร่ใน fabric (deterministic ต่อ seed) → สัดส่วนผู้เชื่อแต่ละฝั่ง"""
    sim = FabricSimulation(personas, seed=seed)
    sim.inject(Message("ours", "rumor", our_move, 1, "public_feed"))
    sim.inject(Message("opp", "rumor", opp_move, 2, "public_feed"))
    result = sim.run(rounds)
    n = len(result.states)
    ours = sum(1 for st in result.states.values() if st.believed.get("ours")) / n
    opp = sum(1 for st in result.states.values() if st.believed.get("opp")) / n
    return ours, opp


def build_tree_prompt(scenario: str, turns: list[GameTurn]) -> str:
    history = "\n".join(
        f"ตา {t.turn_no}: เราเดิน='{t.our_move[:150]}' → ฝ่ายตรงข้ามตอบ='{t.opp_move[:150]}' "
        f"→ สังคมเชื่อฝั่งเรา {t.belief_ours:.0%} / ฝั่งตรงข้าม {t.belief_opp:.0%}"
        for t in turns
    )
    return f"""คุณคือนักวิเคราะห์กลยุทธ์ สรุปเกมจำลองด้านล่างเป็น decision tree

สถานการณ์: \"\"\"{scenario[:1000]}\"\"\"

เส้นทางที่เดินจริง:
{history}

สำหรับแต่ละตา ให้:
- taken: สรุปสั้นๆ ว่าการเดินจริงให้ผลอย่างไร (อ้างตัวเลขความเชื่อจากข้อมูลข้างบนเท่านั้น)
- alternative: ทางเลือกเชิงวิเคราะห์ที่ไม่ได้เดิน 1 ทาง + ผลที่น่าจะเกิด (เชิงทิศทาง ไม่กุตัวเลข)

กติกา (GOV-05): alternative เป็นแนววิเคราะห์เท่านั้น ห้ามร่างข้อความ/สคริปต์สำเร็จรูป
ตอบภาษาไทยเท่านั้น ตอบ JSON เท่านั้น:
{{"nodes": [{{"turn": 1, "taken": "...", "alternative": "..."}}, ...]}}"""


def parse_tree(raw: str, turns: list[GameTurn]) -> list[TreeNode]:
    """parse พัง = tree จากข้อมูลดิบ (ไม่มี alternative) — ผลเกมต้องไม่หาย"""
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            nodes = data.get("nodes", [])
            if len(nodes) == len(turns):
                return [
                    TreeNode(
                        turn_no=int(n.get("turn", i + 1)),
                        taken_summary=str(n.get("taken", ""))[:400],
                        alternative=str(n.get("alternative", ""))[:400],
                    )
                    for i, n in enumerate(nodes)
                ]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return [
        TreeNode(
            turn_no=t.turn_no,
            taken_summary=(
                f"เรา: {t.our_move[:80]} → ตรงข้าม: {t.opp_move[:80]} "
                f"(เชื่อเรา {t.belief_ours:.0%}/เขา {t.belief_opp:.0%})"
            ),
            alternative="(analyst parse พัง — ไม่มีทางเลือกวิเคราะห์)",
        )
        for t in turns
    ]


class GameSession:
    """เกมหนึ่งกระดาน — ผู้เข้าร่วมจำลอง (populations) ≤ cap ช่วงพัฒนา"""

    def __init__(
        self,
        adapter: LLMAdapter,
        scenario: str,
        personas: list[Persona],
        *,
        actor: StrategicActor = OPPOSITION,
        seed: int,
        voices_per_turn: int = 2,
    ):
        self._adapter = adapter
        self._scenario = scenario
        self._personas = personas
        self._actor = actor
        self._seed = seed
        self._voices_per_turn = voices_per_turn
        self.turns: list[GameTurn] = []

    def play_turn(self, our_move: str) -> GameTurn:
        raw = self._adapter.chat(
            ModelTier.ANALYST,  # การเดินเชิงกลยุทธ์ต้องคิดลึก
            [
                {
                    "role": "user",
                    "content": build_opponent_prompt(
                        self._actor, self._scenario, self.turns, our_move
                    ),
                }
            ],
            max_tokens=400,
            seed=self._seed + len(self.turns),
        ).text
        opp_move, rationale = parse_opponent_move(raw)
        belief_ours, belief_opp = society_react(
            self._personas, our_move, opp_move, seed=self._seed + len(self.turns) * 7
        )
        voices: list[str] = []
        for i, persona in enumerate(self._personas[: self._voices_per_turn]):
            v = generate_voice(
                self._adapter,
                persona,
                f"ฝ่ายผลักดันแผน: {our_move[:150]} | ฝ่ายค้าน: {opp_move[:150]}",
                believed=True,
                channel="public_feed",
                seed=self._seed + len(self.turns) * 100 + i,
                reasoning=False,
            )
            if v.public_post:
                voices.append(f"{persona.segment_name}: {v.public_post}")
        turn = GameTurn(
            turn_no=len(self.turns) + 1,
            our_move=our_move,
            opp_move=opp_move,
            opp_rationale=rationale,
            belief_ours=belief_ours,
            belief_opp=belief_opp,
            voices=tuple(voices),
        )
        self.turns.append(turn)
        return turn

    def decision_tree(self) -> list[TreeNode]:
        if len(self.turns) < MIN_TURNS:
            raise ValueError(f"เกมต้องเล่น ≥ {MIN_TURNS} ตาก่อนสรุป decision tree (PRD REH-03)")
        raw = self._adapter.chat(
            ModelTier.ANALYST,
            [{"role": "user", "content": build_tree_prompt(self._scenario, self.turns)}],
            max_tokens=900,
            temperature=0.0,
            seed=self._seed,
        ).text
        return parse_tree(raw, self.turns)


def render_game_report(title: str, turns: list[GameTurn], tree: list[TreeNode]) -> str:
    lines = [
        f"# Game Mode Report (REH-03): {title}",
        "",
        "> ⚠️ เกมจำลองกับ strategic actor — simulation_estimate ไม่ใช่คำทำนายการตอบโต้จริง"
        " | ทางเลือกเป็นแนววิเคราะห์ ไม่ใช่ร่างข้อความ (GOV-05)",
        "",
        f"- จำนวนตา: {len(turns)} (ขั้นต่ำ {MIN_TURNS} ตาม PRD)",
        "",
        "## เส้นทางเกม (เราเดิน → ฝ่ายตรงข้ามตอบ → สังคม react)",
        "",
        "| ตา | เราเดิน | ฝ่ายตรงข้ามตอบ | เชื่อฝั่งเรา | เชื่อฝั่งตรงข้าม |",
        "|---|---|---|---|---|",
    ]
    for t in turns:
        lines.append(
            f"| {t.turn_no} | {t.our_move[:80]} | {t.opp_move[:80]} "
            f"| {t.belief_ours:.0%} | {t.belief_opp:.0%} |"
        )
    lines += ["", "## Decision Tree (เส้นทางจริง + ทางเลือกที่ไม่ได้เดิน)", ""]
    for node in tree:
        lines += [
            f"- **ตา {node.turn_no}** ✅ เดินจริง: {node.taken_summary}",
            f"  - ↘️ ทางเลือก: {node.alternative}",
        ]
    lines += ["", "## เหตุผลฝ่ายตรงข้าม + เสียงสังคมรายตา", ""]
    for t in turns:
        lines += [f"**ตา {t.turn_no}** — ฝ่ายตรงข้ามหวังผล: {t.opp_rationale}"]
        lines += [f"> 💬 {v}" for v in t.voices]
        lines.append("")
    return "\n".join(lines)
