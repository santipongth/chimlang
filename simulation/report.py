"""รายงานพื้นฐาน (M4) — markdown: สรุปรายกลุ่ม + trail ตัวอย่าง + voice share vs population share

voice share vs population share (TRUST-07): สัดส่วน "เสียงที่ปรากฏ" (agent ที่แชร์/แสดงออก)
มักไม่เท่าสัดส่วน "คนจริง" ของกลุ่มนั้น — ทุกรายงานต้องแสดงคู่กันเสมอ
"""

from collections import Counter

from simulation.engine import RunResult
from simulation.experiment import DeltaEstimate, ForkOutcome


def voice_vs_population(result: RunResult, msg_id: str) -> list[tuple[str, float, float]]:
    """คืน (segment_name, population_share, voice_share) — voice = ผู้แชร์ข้อความนี้"""
    seg_of = {aid: st.persona.segment_name for aid, st in result.states.items()}
    pop = Counter(seg_of.values())
    sharers = [aid for aid, st in result.states.items() if st.sharing.get(msg_id)]
    voice = Counter(seg_of[a] for a in sharers)
    total_voice = max(1, len(sharers))
    n = len(result.states)
    return [
        (seg, pop[seg] / n, voice.get(seg, 0) / total_voice)
        for seg in sorted(pop, key=lambda s: -pop[s])
    ]


def render_whatif_report(
    *,
    title: str,
    estimate: DeltaEstimate,
    outcomes: list[ForkOutcome],
    base_msg_id: str,
    event_text: str,
    rounds: int,
) -> str:
    example = outcomes[0]
    lo, hi = estimate.ci95
    sig = "ใช่ (CI ไม่คร่อม 0)" if lo > 0 or hi < 0 else "ไม่ (CI คร่อม 0)"
    lines = [
        f"# รายงาน What-if (SIM-04): {title}",
        "",
        f"- event ที่ inject: {event_text} (round {example.inject_round})",
        f"- seeds: {len(outcomes)} | rounds: {rounds} | agents/run: {len(example.baseline.states)}",
        "",
        "## Delta ของสัดส่วนผู้เชื่อข่าวลือ (variant − baseline)",
        f"- ค่าเฉลี่ย: **{estimate.mean_delta:+.1%}** | ช่วงความเชื่อมั่น 95%: [{lo:+.1%}, {hi:+.1%}]",
        f"- ทิศทางชัดเจนทางสถิติ: {sig}",
        "- ⚠️ ผลนี้เป็น simulation_estimate — บอกทิศทางและโครงสร้าง ไม่ใช่คำทำนายรับประกัน",
        "",
        "## Voice share vs Population share (baseline, seed แรก — TRUST-07)",
        "",
        "| กลุ่ม | population share | voice share |",
        "|---|---|---|",
    ]
    for seg, pop_share, voice_share in voice_vs_population(example.baseline, base_msg_id):
        lines.append(f"| {seg} | {pop_share:.0%} | {voice_share:.0%} |")
    lines += [
        "",
        "## สรุปรายกลุ่ม (belief rate ใน variant, seed แรก)",
        "",
        "| กลุ่ม | เชื่อข่าวลือ (baseline) | เชื่อข่าวลือ (หลัง inject) |",
        "|---|---|---|",
    ]
    def seg_belief(result: RunResult, seg: str) -> float:
        members = [st for st in result.states.values() if st.persona.segment_name == seg]
        return sum(1 for st in members if st.believed.get(base_msg_id)) / max(1, len(members))

    segs = sorted({st.persona.segment_name for st in example.baseline.states.values()})
    for seg in segs:
        lines.append(
            f"| {seg} | {seg_belief(example.baseline, seg):.0%} "
            f"| {seg_belief(example.variant, seg):.0%} |"
        )
    trail_sample = [e for e in example.variant.trail if e["round"] >= example.inject_round][:8]
    lines += [
        "",
        "## ตัวอย่าง reasoning trail (variant, ตั้งแต่ round ที่ inject — NFR-08)",
        "",
        "```",
        *[
            f"r{e['round']:>2} | {e['agent']:<24} | {e['channel']:<18} | {e['action']} ({e['msg']})"
            for e in trail_sample
        ],
        "```",
        "",
        f"(trail เต็ม {len(example.variant.trail)} เหตุการณ์ อยู่ใน RunResult — ทุกตัวเลขย้อนได้)",
    ]
    return "\n".join(lines)
