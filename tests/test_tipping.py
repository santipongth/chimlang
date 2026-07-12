"""tests P5-M2: tipping point detection (PRD pipeline ขั้น 7 — บังคับทุกรายงาน)"""

import pytest

from simulation.engine import FabricSimulation, Message
from simulation.persona import PersonaFactory
from simulation.report import render_whatif_report
from simulation.tipping import (
    TippingPoint,
    belief_series,
    detect_tipping_points,
    tipping_from_run,
)


def _run(seed: int, *, broadcast: float = 0.0, rounds: int = 15):
    personas = PersonaFactory().sample(40, seed=seed, max_agents=40)
    sim = FabricSimulation(personas, seed=seed)
    sim.inject(Message("rumor", "rumor", "ข่าวลือทดสอบ", 1, "public_feed", broadcast_share=broadcast))
    return sim.run(rounds)


# ---- detect_tipping_points (pure function) ----


def test_detect_flags_jump_at_threshold():
    pts = detect_tipping_points([0.0, 0.05, 0.30, 0.32], threshold=0.15)
    assert pts == [TippingPoint(round_no=2, before=0.05, after=0.30, delta=0.25)]


def test_detect_flags_negative_jump_too():
    # คำชี้แจงดึงความเชื่อดิ่งลงก็เป็น tipping (narrative พลิกขาลง)
    pts = detect_tipping_points([0.6, 0.58, 0.30], threshold=0.15)
    assert len(pts) == 1 and pts[0].delta == pytest.approx(-0.28)


def test_detect_no_points_when_gradual():
    assert detect_tipping_points([0.0, 0.1, 0.2, 0.3], threshold=0.15) == []


def test_detect_rejects_bad_threshold():
    with pytest.raises(ValueError):
        detect_tipping_points([0.0, 1.0], threshold=0.0)


# ---- belief_series จาก reasoning trail ----


def test_belief_series_bounds_and_length():
    result = _run(seed=11)
    series = belief_series(result, "rumor")
    assert len(series) == result.rounds + 1
    assert all(0.0 <= v <= 1.0 for v in series)
    assert series[0] == 0.0  # ไม่มี preseed → เริ่มศูนย์


def test_belief_series_deterministic_per_seed():
    a = belief_series(_run(seed=7), "rumor")
    b = belief_series(_run(seed=7), "rumor")
    assert a == b


def test_belief_series_matches_final_state():
    # ค่าปลาย series ต้องตรงกับการนับ believed จาก state จริง (ยอดเชื่อสุทธิหลัง revision)
    result = _run(seed=5)
    series = belief_series(result, "rumor")
    truth = sum(1 for st in result.states.values() if st.believed.get("rumor")) / len(result.states)
    assert series[-1] == pytest.approx(truth)


def test_broadcast_release_creates_tipping():
    # โหมดสื่อมวลชน 60% ของประชากรใน round เดียว → ต้องเกิด tipping ขาขึ้น
    result = _run(seed=3, broadcast=0.6)
    pts = tipping_from_run(result, "rumor")
    assert pts and pts[0].delta > 0


# ---- บังคับในรายงาน (PRD ขั้น 7) ----


def test_whatif_report_always_has_tipping_section():
    from simulation.experiment import fork_run

    personas = PersonaFactory().sample(10, seed=2, max_agents=10)
    outcome = fork_run(
        personas,
        seed=2,
        rounds=20,
        base_messages=[Message("rumor", "rumor", "ข่าวลือทดสอบ", 1, "public_feed")],
        event=Message("official", "correction", "คำชี้แจงทดสอบ", 8, "public_feed", counters="rumor"),
    )
    from simulation.experiment import DeltaEstimate, belief_rate

    delta = belief_rate(outcome.variant, "rumor") - belief_rate(outcome.baseline, "rumor")
    report = render_whatif_report(
        title="ทดสอบ",
        estimate=DeltaEstimate.from_deltas("belief_rate(rumor)", [delta, delta]),
        outcomes=[outcome],
        base_msg_id="rumor",
        event_text="คำชี้แจงทดสอบ",
        rounds=20,
    )
    assert "Tipping Points" in report  # ต้องมี section เสมอ แม้ไม่พบจุดพลิก
