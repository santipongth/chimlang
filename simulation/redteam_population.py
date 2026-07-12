"""Red Team in-population (P5-M4) — REH-02 ภาคปฏิบัติแบบวัดผลเป็นตัวเลข

ต่างจาก Red Team Swarm เดิม (simulation/redteam.py = LLM ผลิต Attack Surface Report):
โหมดนี้ **ฝัง adversarial agents ลงใน population จริง** แล้วรันคู่กับ baseline
ด้วย seed เดียวกัน เพื่อวัดว่าข้อสรุปหลัก (delta ของคำชี้แจง) ทนต่อผู้เล่นปฏิปักษ์
ที่เสียงดังและต้านคำชี้แจงได้แค่ไหน — แนวคิดจาก SwarmSight (contrarian + auditor)
แปลงเข้ากลไก diffusion ของเรา:

- เสียงดังสุด (voice_activity 1.0) ไม่เกรงใจ (kreng_jai 0) ไม่มี say-do gap
- ต้านคำชี้แจงทางการ: correction_receptivity ต่ำ (เชื่อข่าวแก้ยากมาก)
- contrarian อยู่หนัก public feed (ปั่นกระแสสาธารณะ), auditor อยู่หนักกลุ่มปิด
  (ปลุกความสงสัยในวงที่ตรวจสอบยากที่สุด)

GOV-05: ผลลัพธ์ = ตัวเลขความทน (robustness) เท่านั้น — ห้ามผลิตสารตอบโต้จากผลนี้
"""

from simulation.persona import Persona

RED_TEAM_SEGMENT = "Red Team (adversarial)"

RED_TEAM: tuple[Persona, ...] = (
    Persona(
        agent_id="redteam-contrarian",
        segment_id="redteam",
        segment_name=RED_TEAM_SEGMENT,
        channel_mix={
            "public_feed": 0.55,
            "algo_feed": 0.30,
            "line_closed_group": 0.10,
            "offline_wom": 0.05,
        },
        voice_activity=1.0,
        kreng_jai=0.0,
        say_do_gap=0.0,
        sarcasm_meme=0.9,
        traits=("redteam", "contrarian"),
        correction_receptivity=0.1,
    ),
    Persona(
        agent_id="redteam-auditor",
        segment_id="redteam",
        segment_name=RED_TEAM_SEGMENT,
        channel_mix={
            "line_closed_group": 0.50,
            "public_feed": 0.25,
            "algo_feed": 0.15,
            "offline_wom": 0.10,
        },
        voice_activity=1.0,
        kreng_jai=0.0,
        say_do_gap=0.0,
        sarcasm_meme=0.5,
        traits=("redteam", "auditor"),
        correction_receptivity=0.1,
    ),
)


def inject_red_team(personas: list[Persona]) -> list[Persona]:
    """แทนที่ 2 ตัวสุดท้ายด้วย adversarial agents — จำนวนรวมเท่าเดิม (ไม่กระทบ cap)

    population < 4 = เล็กเกินกว่าจะมีความหมาย (red team จะกลายเป็นเสียงข้างมาก) → ปฏิเสธ
    """
    if len(personas) < 4:
        raise ValueError("population ต้อง ≥ 4 ก่อนฝัง red team (ไม่งั้น adversarial เป็นเสียงข้างมาก)")
    return personas[: len(personas) - len(RED_TEAM)] + list(RED_TEAM)
