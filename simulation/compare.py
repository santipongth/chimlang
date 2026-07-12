"""Compare mode (P5-M4): baseline vs +Red Team ด้วยชุด seed เดียวกัน — วัด groupthink เป็นตัวเลข

คำถามที่โหมดนี้ตอบ: "ข้อสรุปหลัก (คำชี้แจงลดความเชื่อข่าวลือได้เท่าไหร่) ยังยืนอยู่ไหม
ถ้ามีผู้เล่นปฏิปักษ์เสียงดัง 2 ตัวฝังใน population?" — ทุกอย่างเหมือนกันเป๊ะยกเว้น
2 agents สุดท้าย ⇒ ความต่างของ delta อธิบายได้จาก red team เท่านั้น (controlled experiment)
"""

from collections import defaultdict

from simulation.engine import Message, RunResult
from simulation.experiment import DeltaEstimate, run_whatif
from simulation.persona import PersonaFactory
from simulation.redteam_population import RED_TEAM, RED_TEAM_SEGMENT, inject_red_team
from trust.universe import conclusion_of


def _belief_by_segment(result: RunResult, msg_id: str) -> dict[str, float]:
    agg: dict[str, list[bool]] = defaultdict(list)
    for st in result.states.values():
        agg[st.persona.segment_name].append(bool(st.believed.get(msg_id)))
    return {seg: sum(v) / len(v) for seg, v in sorted(agg.items())}


def _side(estimate: DeltaEstimate, variant: RunResult, msg_id: str) -> dict:
    lo, hi = estimate.ci95
    return {
        "mean_delta": estimate.mean_delta,
        "ci95": [lo, hi],
        "conclusion": conclusion_of(estimate),
        "belief_by_segment": _belief_by_segment(variant, msg_id),
    }


def run_redteam_compare(
    factory: PersonaFactory,
    *,
    n_agents: int,
    max_agents: int,
    rounds: int,
    base_messages: list[Message],
    event: Message,
    target_msg_id: str,
    seeds: list[int],
) -> dict:
    """รันคู่ baseline / +red team ด้วย seeds ชุดเดียวกัน → ผลเทียบ + ความทนของข้อสรุป"""
    base_est, base_outcomes = run_whatif(
        lambda s: factory.sample(n_agents, seed=s, max_agents=max_agents),
        seeds=list(seeds),
        rounds=rounds,
        base_messages=list(base_messages),
        event=event,
        target_msg_id=target_msg_id,
    )
    rt_est, rt_outcomes = run_whatif(
        lambda s: inject_red_team(factory.sample(n_agents, seed=s, max_agents=max_agents)),
        seeds=list(seeds),
        rounds=rounds,
        base_messages=list(base_messages),
        event=event,
        target_msg_id=target_msg_id,
    )
    baseline = _side(base_est, base_outcomes[0].variant, target_msg_id)
    red_team = _side(rt_est, rt_outcomes[0].variant, target_msg_id)
    return {
        "seeds": list(seeds),
        "rounds": rounds,
        "agents": n_agents,
        "baseline": baseline,
        "red_team": {
            **red_team,
            "roster": [{"agent_id": p.agent_id, "traits": list(p.traits)} for p in RED_TEAM],
            "segment_label": RED_TEAM_SEGMENT,
        },
        # delta_of_delta > 0 = red team ทำให้คำชี้แจงได้ผล "น้อยลง" เท่านี้ (จุดอ่อนของแผนสื่อสาร)
        "delta_of_delta": rt_est.mean_delta - base_est.mean_delta,
        "robust": conclusion_of(base_est) == conclusion_of(rt_est),
        "note": (
            "controlled experiment: ทุกอย่างเหมือนกันยกเว้น 2 agents สุดท้ายถูกแทนด้วย "
            "adversarial (เสียงดังสุด ไม่เกรงใจ ต้านคำชี้แจง) — GOV-05: ใช้วัดความทนเท่านั้น "
            "ห้ามนำไปผลิตสารตอบโต้"
        ),
    }
