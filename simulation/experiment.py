"""Injectable Events (SIM-04) — fork 2 branches จาก seed เดียวกัน เทียบ delta

AC: inject event ที่ round N → branch (baseline ไม่มี event / variant มี event)
ต้อง identical จนถึงก่อน round N แล้วรายงาน delta ของ adoption/belief พร้อมช่วงความเชื่อมั่น

กลไก: engine เป็น deterministic เต็มรูป และ message ที่ยังไม่ถึง start_round ไม่กิน RNG
→ append event ต่อท้าย message list ทำให้ 2 branches ใช้ RNG sequence เดียวกันจนถึง round N
(มี verify_identical_until ตรวจจริง ไม่ใช่เชื่อโครงสร้างอย่างเดียว)
"""

from dataclasses import dataclass
from statistics import mean, stdev

from simulation.engine import FabricSimulation, Message, RunResult
from simulation.persona import Persona


@dataclass(frozen=True)
class ForkOutcome:
    seed: int
    baseline: RunResult
    variant: RunResult
    inject_round: int


def fork_run(
    personas: list[Persona],
    *,
    seed: int,
    rounds: int,
    base_messages: list[Message],
    event: Message,
) -> ForkOutcome:
    baseline_sim = FabricSimulation(personas, seed=seed)
    variant_sim = FabricSimulation(personas, seed=seed)
    for m in base_messages:
        baseline_sim.inject(m)
        variant_sim.inject(m)
    variant_sim.inject(event)  # ต่อท้ายเสมอ — รักษา RNG alignment ก่อน start_round
    outcome = ForkOutcome(
        seed=seed,
        baseline=baseline_sim.run(rounds),
        variant=variant_sim.run(rounds),
        inject_round=event.start_round,
    )
    if not verify_identical_until(outcome, event.start_round):
        raise AssertionError(
            f"fork ไม่ identical ก่อน round {event.start_round} (seed {seed}) — AC ของ SIM-04 แตก"
        )
    return outcome


def verify_identical_until(outcome: ForkOutcome, round_n: int) -> bool:
    """trail ของสอง branch ต้องตรงกันทุกเหตุการณ์ที่ round < round_n"""
    pre = lambda trail: [e for e in trail if e["round"] < round_n]  # noqa: E731
    return pre(outcome.baseline.trail) == pre(outcome.variant.trail)


def belief_rate(result: RunResult, msg_id: str) -> float:
    n = len(result.states)
    return sum(1 for st in result.states.values() if st.believed.get(msg_id)) / n


@dataclass(frozen=True)
class DeltaEstimate:
    metric: str
    per_seed: tuple[float, ...]  # delta (variant - baseline) ต่อ seed
    mean_delta: float
    ci95: tuple[float, float]  # normal approx: mean ± 1.96·sd/√n

    @classmethod
    def from_deltas(cls, metric: str, deltas: list[float]) -> "DeltaEstimate":
        m = mean(deltas)
        half = 1.96 * stdev(deltas) / len(deltas) ** 0.5 if len(deltas) > 1 else float("inf")
        return cls(metric=metric, per_seed=tuple(deltas), mean_delta=m, ci95=(m - half, m + half))


def run_whatif(
    personas_by_seed,
    *,
    seeds: list[int],
    rounds: int,
    base_messages: list[Message],
    event: Message,
    target_msg_id: str,
) -> tuple[DeltaEstimate, list[ForkOutcome]]:
    """รัน fork ข้ามหลาย seed → delta ของ belief rate ต่อ target message + CI

    personas_by_seed: callable(seed) -> personas (ให้ population เปลี่ยนตาม seed ด้วย
    เพื่อให้ CI สะท้อนความไม่แน่นอนของทั้ง population และ dynamics)
    """
    outcomes = [
        fork_run(
            personas_by_seed(seed),
            seed=seed,
            rounds=rounds,
            base_messages=list(base_messages),
            event=event,
        )
        for seed in seeds
    ]
    deltas = [
        belief_rate(o.variant, target_msg_id) - belief_rate(o.baseline, target_msg_id)
        for o in outcomes
    ]
    return DeltaEstimate.from_deltas(f"belief_rate({target_msg_id})", deltas), outcomes
