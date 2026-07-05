"""Multi-Universe Orchestrator + Fragility Index (TRUST-04/05)

ตอบความเสี่ยงอันดับหนึ่งของ PRD — Synthetic Consensus: ผลรอบเดียวอาจสะท้อน bias
ของสมมติฐานมากกว่าสังคมจริง จึงรัน ≥ 5 universes โดยเขย่าสมมติฐาน (สัดส่วน segment
±10%, seed) แล้ววัดว่า "ข้อสรุปหลัก" พลิกง่ายแค่ไหน

- Fragility Index 0–100 = % ของ universes ที่ข้อสรุปไม่ตรงกับเสียงข้างมาก
- TRUST-05: > 40 → downgrade label + คำเตือนเด่น | > 70 → ห้ามรายงานตัวเลขเดี่ยว (ช่วงเท่านั้น)
"""

from collections import Counter
from dataclasses import dataclass

from simulation.engine import Message
from simulation.experiment import DeltaEstimate, run_whatif
from simulation.persona import PersonaFactory

DOWNGRADE_THRESHOLD = 40
BLOCK_POINT_ESTIMATE_THRESHOLD = 70


def conclusion_of(estimate: DeltaEstimate) -> str:
    """ข้อสรุปหลักของหนึ่ง universe จากทิศทาง delta + CI"""
    lo, hi = estimate.ci95
    if hi < 0:
        return "ลดลง"
    if lo > 0:
        return "เพิ่มขึ้น"
    return "ไม่ชัด"


@dataclass(frozen=True)
class UniverseResult:
    universe_id: int
    perturb_seed: int | None  # None = universe ฐาน (ไม่เขย่า)
    estimate: DeltaEstimate
    conclusion: str


@dataclass(frozen=True)
class FragilityReport:
    universes: tuple[UniverseResult, ...]
    majority_conclusion: str
    fragility_index: int  # 0-100

    @property
    def confidence_label(self) -> str:
        if self.fragility_index > BLOCK_POINT_ESTIMATE_THRESHOLD:
            return "พลิกง่ายมาก — ห้ามรายงานตัวเลขเดี่ยว ใช้ช่วงเท่านั้น"
        if self.fragility_index > DOWNGRADE_THRESHOLD:
            return "เปราะบาง — ความเชื่อมั่นถูกลดระดับอัตโนมัติ"
        return "มั่นคงต่อการเขย่าสมมติฐาน"

    @property
    def block_point_estimate(self) -> bool:
        return self.fragility_index > BLOCK_POINT_ESTIMATE_THRESHOLD

    @property
    def downgraded(self) -> bool:
        return self.fragility_index > DOWNGRADE_THRESHOLD


def fragility_from(universes: list[UniverseResult]) -> FragilityReport:
    counts = Counter(u.conclusion for u in universes)
    majority, _ = counts.most_common(1)[0]
    flipped = sum(1 for u in universes if u.conclusion != majority)
    return FragilityReport(
        universes=tuple(universes),
        majority_conclusion=majority,
        fragility_index=round(100 * flipped / len(universes)),
    )


def run_multiverse_whatif(
    base_factory: PersonaFactory,
    *,
    n_agents: int,
    max_agents: int,
    universes: int = 5,
    seeds_per_universe: int = 20,
    rounds: int,
    base_messages: list[Message],
    event: Message,
    target_msg_id: str,
    base_seed: int = 42,
    on_progress=None,
) -> FragilityReport:
    """what-if เดิมซ้ำใน ≥5 universes: u0 = สมมติฐานฐาน, u1.. = เขย่า share ±10% + ชุด seed ใหม่"""
    if universes < 5:
        raise ValueError("TRUST-04 กำหนดอย่างน้อย 5 universes")
    results: list[UniverseResult] = []
    base_outcomes = []
    for u in range(universes):
        perturb_seed = None if u == 0 else base_seed * 1000 + u
        factory = (
            base_factory if perturb_seed is None else base_factory.perturb_shares(seed=perturb_seed)
        )
        universe_seeds = [base_seed + u * seeds_per_universe + i for i in range(seeds_per_universe)]
        estimate, outcomes = run_whatif(
            lambda s, f=factory: f.sample(n_agents, seed=s, max_agents=max_agents),
            seeds=universe_seeds,
            rounds=rounds,
            base_messages=list(base_messages),
            event=event,
            target_msg_id=target_msg_id,
        )
        if u == 0:
            base_outcomes = outcomes  # ใช้ทำ trail/voice-share ในรายงาน (สมมติฐานฐาน)
        result = UniverseResult(
            universe_id=u,
            perturb_seed=perturb_seed,
            estimate=estimate,
            conclusion=conclusion_of(estimate),
        )
        results.append(result)
        if on_progress:
            on_progress(result)
    return fragility_from(results), base_outcomes
