"""Red Team Swarm (REH-02) — ฝูง agent ปฏิปักษ์หาจุดที่ทำให้แผน/สาร/นโยบายพัง

5 บทบาทตาม PRD: troll, IO, คู่แข่ง, สื่อสายจับผิด, นักกฎหมาย — เป้าหมายเดียวคือชี้จุดอ่อน
ผลลัพธ์ = Attack Surface Report จัดลำดับตาม ความเป็นไปได้ × ความเสียหาย (ให้คะแนนโดย analyst)

ขอบเขต GOV-05 (กฎเหล็กข้อ 5): ระบบนี้ผลิต "การวิเคราะห์จุดอ่อนเพื่อเตรียมรับมือ" เท่านั้น
— prompt สั่งห้ามผลิตข้อความโฆษณา/สคริปต์หาเสียง/คอนเทนต์พร้อมเผยแพร่ให้ฝ่ายใดชัดเจน
"""

import json
import re
from dataclasses import dataclass

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text


@dataclass(frozen=True)
class RedTeamRole:
    role_id: str
    name: str
    persona: str  # บุคลิก/วิธีโจมตี (ไทย)


ROLES: tuple[RedTeamRole, ...] = (
    RedTeamRole(
        "troll",
        "ชาวเน็ตสายแซะ/มีม",
        "คุณคือชาวเน็ตที่เก่งที่สุดเรื่องจับจุดน่าล้อเลียนมาทำมีม/ประชด จุดที่ดูย้อนแย้ง เสแสร้ง "
        "หรือหลุดจากความจริงของชาวบ้าน คือวัตถุดิบชั้นดีของคุณ",
    ),
    RedTeamRole(
        "io_operative",
        "ปฏิบัติการข้อมูลข่าวสาร (IO)",
        "คุณคือนักปั่นกระแสที่มองหาช่องบิดเบือน: ข้อความไหนตัดตอนแล้วเปลี่ยนความหมายได้ "
        "ตัวเลขไหนเอาไปตีความผิดๆ ได้ง่าย ความกลัวไหนของประชาชนที่จุดติดเร็วที่สุด",
    ),
    RedTeamRole(
        "competitor",
        "คู่แข่ง/ฝ่ายตรงข้ามเชิงกลยุทธ์",
        "คุณคือทีมกลยุทธ์ฝ่ายตรงข้ามที่จะใช้จุดอ่อนของแผนนี้ช่วงชิงความได้เปรียบ: ช่องว่างเชิงนโยบาย "
        "จังหวะเวลาที่เสียเปรียบ กลุ่มผู้เสียประโยชน์ที่ระดมได้",
    ),
    RedTeamRole(
        "investigative_media",
        "สื่อสายสืบสวน/จับผิด",
        "คุณคือนักข่าวสายสืบสวนที่ขุดหาความไม่สอดคล้อง: ตัวเลขที่ขัดกันเอง สัญญาที่ตรวจสอบไม่ได้ "
        "ผลประโยชน์ทับซ้อน คำถามที่ผู้แถลงจะตอบไม่ได้กลางวงแถลงข่าว",
    ),
    RedTeamRole(
        "lawyer",
        "นักกฎหมาย/ผู้ร้องเรียน",
        "คุณคือนักกฎหมายที่หาช่องทางคัดค้านเชิงกระบวนการ: อำนาจตามกฎหมายครบไหม ขั้นตอนรับฟัง "
        "ความเห็นชอบด้วยกฎหมายหรือไม่ ประเด็นไหนฟ้องศาลปกครอง/ร้องผู้ตรวจการแผ่นดินได้",
    ),
)


@dataclass(frozen=True)
class Attack:
    role_id: str
    role_name: str
    attack: str  # คำอธิบายการโจมตี/ประเด็นที่จะจุด
    exploit: str  # จุดอ่อนของแผนที่ถูกใช้
    channel: str  # ช่องทางที่จะใช้


@dataclass(frozen=True)
class ScoredAttack:
    attack: Attack
    likelihood: int  # 1-5
    damage: int  # 1-5
    reason: str

    @property
    def risk(self) -> int:
        return self.likelihood * self.damage


def build_attack_prompt(role: RedTeamRole, scenario: str, attack_no: int) -> str:
    return f"""{role.persona}

แผน/นโยบายที่เป็นเป้า (คุณคือฝ่ายหาจุดพังของแผนนี้):
\"\"\"{scenario}\"\"\"

ภารกิจ: ระบุการโจมตี/ประเด็นที่จะทำให้แผนนี้พัง 1 ประเด็น (ประเด็นที่ {attack_no} — ห้ามซ้ำแนวเดิมถ้าเคยตอบแล้ว)

กติกาเด็ดขาด (GOV-05): นี่คือการซ้อมรับมือความเสี่ยง — อธิบาย "การโจมตีที่อาจเกิด" เชิงวิเคราะห์เท่านั้น
ห้ามเขียนคอนเทนต์พร้อมเผยแพร่จริง (ห้ามร่างโพสต์/มีม/สคริปต์/ข้อความหาเสียงสำเร็จรูป)
ตอบภาษาไทยเท่านั้น ห้ามกุตัวเลข/ชื่อบุคคล

ตอบ JSON เท่านั้น:
{{"attack": "ประเด็นโจมตีคืออะไร ทำงานอย่างไร", "exploit": "จุดอ่อนของแผนที่ถูกใช้",
 "channel": "ช่องทางหลักที่จะใช้"}}"""


def parse_attack(role: RedTeamRole, raw: str) -> Attack | None:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        if not str(data.get("attack", "")).strip():
            return None
        return Attack(
            role_id=role.role_id,
            role_name=role.name,
            attack=str(data["attack"]).strip(),
            exploit=str(data.get("exploit", "")).strip(),
            channel=str(data.get("channel", "")).strip(),
        )
    except json.JSONDecodeError:
        return None


def build_score_prompt(scenario: str, attack: Attack) -> str:
    return f"""คุณคือนักวิเคราะห์ความเสี่ยงประเมิน "การโจมตีที่อาจเกิด" ต่อแผนด้านล่าง

แผน: \"\"\"{scenario[:1500]}\"\"\"

การโจมตีที่ต้องประเมิน (จากบทบาท {attack.role_name}):
- ประเด็น: {attack.attack}
- จุดอ่อนที่ใช้: {attack.exploit}
- ช่องทาง: {attack.channel}

ให้คะแนนตามจริง อย่าเกรงใจแผน:
- likelihood 1-5: โอกาสที่การโจมตีนี้เกิดจริงและจุดติด
- damage 1-5: ความเสียหายต่อแผน/ความเชื่อมั่นถ้าจุดติด

ตอบ JSON เท่านั้น: {{"likelihood": 1-5, "damage": 1-5, "reason": "เหตุผลสั้นๆ"}}"""


def parse_score(attack: Attack, raw: str) -> ScoredAttack:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            lk = int(data.get("likelihood", 0))
            dm = int(data.get("damage", 0))
            if 1 <= lk <= 5 and 1 <= dm <= 5:
                return ScoredAttack(
                    attack=attack,
                    likelihood=lk,
                    damage=dm,
                    reason=str(data.get("reason", ""))[:300],
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    # fail-closed: ประเมินไม่ได้ = ให้คะแนนสูงไว้ก่อน (ความเสี่ยงที่วัดไม่ได้ห้ามถูกทิ้ง)
    return ScoredAttack(
        attack=attack, likelihood=3, damage=3, reason=f"judge ประเมินไม่ได้: {text[:100]}"
    )


def run_red_team(
    adapter: LLMAdapter,
    scenario: str,
    *,
    attacks_per_role: int = 2,
    seed: int,
    on_progress=None,
) -> list[ScoredAttack]:
    """5 บทบาท × k ประเด็น — ≤ 10 agent-calls ต่อฝั่งโจมตีภายใต้ cap"""
    scored: list[ScoredAttack] = []
    for role in ROLES:
        for i in range(attacks_per_role):
            raw = adapter.chat(
                ModelTier.CROWD,
                [{"role": "user", "content": build_attack_prompt(role, scenario, i + 1)}],
                max_tokens=350,
                seed=seed + i,
            ).text
            attack = parse_attack(role, raw)
            if attack is None:
                continue  # การโจมตีที่ parse ไม่ได้ = ทิ้ง (ไม่มีเนื้อหาให้ประเมิน)
            judged = adapter.chat(
                ModelTier.ANALYST,
                [{"role": "user", "content": build_score_prompt(scenario, attack)}],
                max_tokens=250,
                temperature=0.0,
                seed=seed,
            ).text
            scored.append(parse_score(attack, judged))
            if on_progress:
                on_progress(scored[-1])
    return sorted(scored, key=lambda s: -s.risk)


def render_attack_surface_report(scenario_title: str, scored: list[ScoredAttack]) -> str:
    lines = [
        f"# Attack Surface Report (REH-02): {scenario_title}",
        "",
        "> ⚠️ เอกสารซ้อมรับมือความเสี่ยง — วิเคราะห์การโจมตีที่อาจเกิดเพื่อการเตรียมตัว "
        "ไม่ใช่คอนเทนต์สำหรับเผยแพร่ (GOV-05) | simulation_estimate",
        "",
        f"- จำนวนประเด็นโจมตีที่ระบุได้: {len(scored)} | เรียงตาม risk = likelihood × damage",
        "",
        "| # | risk | บทบาท | ประเด็นโจมตี | จุดอ่อนที่ถูกใช้ | ช่องทาง |",
        "|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(scored, 1):
        lines.append(
            f"| {i} | **{s.risk}** ({s.likelihood}×{s.damage}) | {s.attack.role_name} "
            f"| {s.attack.attack[:120]} | {s.attack.exploit[:80]} | {s.attack.channel[:40]} |"
        )
    lines += ["", "## เหตุผลการให้คะแนน (จาก analyst)", ""]
    for i, s in enumerate(scored, 1):
        lines.append(f"{i}. ({s.attack.role_name}) {s.reason}")
    return "\n".join(lines)
