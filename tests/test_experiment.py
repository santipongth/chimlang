"""tests M4: fork determinism (AC ของ SIM-04), delta/CI math, report fields"""

import pytest

from simulation.engine import Message
from simulation.experiment import DeltaEstimate, belief_rate, fork_run, verify_identical_until
from simulation.persona import PersonaFactory
from simulation.report import render_whatif_report, voice_vs_population

RUMOR = Message("rumor", "rumor", "ข่าวลือทดสอบ", 1, "public_feed")


def _fork(seed: int, inject_round: int = 8):
    personas = PersonaFactory().sample(10, seed=seed, max_agents=10)
    return fork_run(
        personas,
        seed=seed,
        rounds=25,
        base_messages=[RUMOR],
        event=Message("official", "correction", "คำชี้แจงทดสอบ", inject_round, "public_feed"),
    )


def test_fork_identical_until_inject_round():
    # AC ของ SIM-04: สอง branch ต้อง identical จนถึงก่อน round N (fork_run assert เองด้วย)
    outcome = _fork(seed=3)
    assert verify_identical_until(outcome, outcome.inject_round)


def test_fork_diverges_after_inject_in_some_seed():
    diverged = any(_fork(seed=s).baseline.trail != _fork(seed=s).variant.trail for s in range(5))
    assert diverged, "inject event แล้วไม่มี seed ไหน diverge เลย — event ไม่มีผลจริง"


def test_baseline_unaffected_by_variant_event():
    outcome = _fork(seed=4)
    assert all(e["msg"] != "official" for e in outcome.baseline.trail)
    assert 0.0 <= belief_rate(outcome.baseline, "rumor") <= 1.0


def test_delta_estimate_math():
    est = DeltaEstimate.from_deltas("m", [-0.2, -0.1, -0.3, -0.2])
    assert est.mean_delta == pytest.approx(-0.2)
    lo, hi = est.ci95
    assert lo < -0.2 < hi
    assert hi < 0  # ทุกค่าติดลบชัด → CI ไม่คร่อม 0


def test_report_contains_required_fields():
    personas = PersonaFactory().sample(10, seed=1, max_agents=10)
    outcome = fork_run(
        personas,
        seed=1,
        rounds=25,
        base_messages=[RUMOR],
        event=Message("official", "correction", "คำชี้แจง", 8, "public_feed"),
    )
    est = DeltaEstimate.from_deltas("belief", [-0.1, -0.2, -0.15])
    report = render_whatif_report(
        title="t",
        estimate=est,
        outcomes=[outcome],
        base_msg_id="rumor",
        event_text="คำชี้แจง",
        rounds=25,
    )
    # field บังคับตาม brief + TRUST-07 + กติกา "ไม่มีตัวเลขเดี่ยวลอยๆ"
    assert "Voice share vs Population share" in report
    assert "ช่วงความเชื่อมั่น 95%" in report
    assert "reasoning trail" in report
    assert "simulation_estimate" in report


def test_belief_revision_reduces_rumor_belief_on_average():
    # correction ที่ counters="rumor" ต้องดึง belief rate ของข่าวลือลงโดยเฉลี่ยข้าม seeds
    from simulation.experiment import run_whatif

    factory = PersonaFactory()
    est, outcomes = run_whatif(
        lambda s: factory.sample(10, seed=s, max_agents=10),
        seeds=list(range(20)),
        rounds=30,
        base_messages=[RUMOR],
        event=Message("official", "correction", "คำชี้แจง", 8, "public_feed", counters="rumor"),
        target_msg_id="rumor",
    )
    assert est.mean_delta < 0, f"belief revision ไม่ทำงาน: delta = {est.mean_delta:+.2%}"
    # trail ต้องมีเหตุการณ์ revised ให้ย้อนตรวจได้ (NFR-08)
    assert any(e["action"] == "revised:rumor" for o in outcomes for e in o.variant.trail)


def test_voice_vs_population_shares_sum():
    personas = PersonaFactory().sample(10, seed=2, max_agents=10)
    outcome = fork_run(
        personas,
        seed=2,
        rounds=25,
        base_messages=[RUMOR],
        event=Message("official", "correction", "คำชี้แจง", 8, "public_feed"),
    )
    rows = voice_vs_population(outcome.baseline, "rumor")
    assert sum(pop for _, pop, _ in rows) == pytest.approx(1.0)
