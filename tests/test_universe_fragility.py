"""tests P1-M1: perturbation, fragility math, threshold 40/70, report coverage/block"""

import pytest

from simulation.engine import Message
from simulation.experiment import DeltaEstimate
from simulation.persona import PersonaFactory
from trust.universe import (
    FragilityReport,
    UniverseResult,
    conclusion_of,
    fragility_from,
    run_multiverse_whatif,
)

RUMOR = Message("rumor", "rumor", "ข่าวลือทดสอบ", 1, "public_feed")
CORR = Message("official", "correction", "คำชี้แจง", 8, "public_feed", counters="rumor")


def _universe(uid: int, conclusion: str) -> UniverseResult:
    est = DeltaEstimate(metric="m", per_seed=(-0.1, -0.2), mean_delta=-0.15, ci95=(-0.2, -0.1))
    return UniverseResult(universe_id=uid, perturb_seed=uid, estimate=est, conclusion=conclusion)


def test_perturb_shares_normalized_and_deterministic():
    base = PersonaFactory()
    p1 = base.perturb_shares(seed=7)
    p2 = base.perturb_shares(seed=7)
    p3 = base.perturb_shares(seed=8)
    assert sum(s["share"] for s in p1.segments) == pytest.approx(1.0)
    assert [s["share"] for s in p1.segments] == [s["share"] for s in p2.segments]  # deterministic
    assert [s["share"] for s in p1.segments] != [s["share"] for s in p3.segments]
    assert [s["share"] for s in p1.segments] != [s["share"] for s in base.segments]  # เขย่าจริง
    # ±10%: ไม่มี segment ไหนเพี้ยนเกินเหตุหลัง normalize
    for orig, pert in zip(base.segments, p1.segments, strict=True):
        assert pert["share"] == pytest.approx(orig["share"], rel=0.25)


def test_conclusion_of_directions():
    down = DeltaEstimate("m", (-0.2,), -0.2, (-0.3, -0.1))
    up = DeltaEstimate("m", (0.2,), 0.2, (0.1, 0.3))
    unclear = DeltaEstimate("m", (0.0,), 0.0, (-0.1, 0.1))
    assert conclusion_of(down) == "ลดลง"
    assert conclusion_of(up) == "เพิ่มขึ้น"
    assert conclusion_of(unclear) == "ไม่ชัด"


def test_fragility_index_math_and_labels():
    all_agree = fragility_from([_universe(i, "ลดลง") for i in range(5)])
    assert all_agree.fragility_index == 0
    assert not all_agree.downgraded and not all_agree.block_point_estimate

    two_flip = fragility_from(
        [_universe(0, "ลดลง"), _universe(1, "ลดลง"), _universe(2, "ลดลง")]
        + [_universe(3, "ไม่ชัด"), _universe(4, "เพิ่มขึ้น")]
    )
    assert two_flip.fragility_index == 40
    assert not two_flip.downgraded  # เกณฑ์คือ "เกิน 40" — 40 พอดียังไม่ downgrade

    heavy = fragility_from(
        [_universe(0, "ลดลง"), _universe(1, "ลดลง")]
        + [_universe(i, c) for i, c in enumerate(["ไม่ชัด"] * 4 + ["เพิ่มขึ้น"] * 4, start=2)]
    )
    assert heavy.fragility_index == 60  # majority = ไม่ชัด(4), พลิก 6/10
    assert heavy.downgraded and not heavy.block_point_estimate

    broken = fragility_from(
        [_universe(0, "ลดลง")]
        + [
            _universe(i, c)
            for i, c in enumerate(
                ["ไม่ชัด", "เพิ่มขึ้น", "ไม่ชัด", "เพิ่มขึ้น", "ลดลง", "เพิ่มขึ้น", "ไม่ชัด", "เพิ่มขึ้น", "เพิ่มขึ้น"],
                start=1,
            )
        ]
    )
    assert broken.fragility_index > 40


def test_block_point_estimate_over_70():
    # 10 universes: majority แค่ 2 → พลิก 8/10 = 80 → block ตัวเลขเดี่ยว
    conclusions = ["ลดลง", "ลดลง"] + ["ไม่ชัด", "เพิ่มขึ้น"] * 4
    fr = fragility_from([_universe(i, c) for i, c in enumerate(conclusions)])
    assert fr.fragility_index == 60  # majority = ไม่ชัด/เพิ่มขึ้น (4 เสียง)... นับจริงตาม Counter
    # สร้างเคส block ชัดๆ: 1 เสียงข้างมากจาก 10 ไม่มีทาง — ใช้ FragilityReport ตรง
    forced = FragilityReport(universes=(), majority_conclusion="ลดลง", fragility_index=80)
    assert forced.block_point_estimate and forced.downgraded
    assert "ห้ามรายงานตัวเลขเดี่ยว" in forced.confidence_label


def test_run_multiverse_end_to_end_mechanistic():
    fragility, base_outcomes = run_multiverse_whatif(
        PersonaFactory(),
        n_agents=10,
        max_agents=10,
        universes=5,
        seeds_per_universe=4,
        rounds=20,
        base_messages=[RUMOR],
        event=CORR,
        target_msg_id="rumor",
        base_seed=42,
    )
    assert len(fragility.universes) == 5
    assert fragility.universes[0].perturb_seed is None  # u0 = สมมติฐานฐาน
    assert all(u.perturb_seed is not None for u in fragility.universes[1:])
    assert 0 <= fragility.fragility_index <= 100
    assert base_outcomes  # ได้ outcomes ของ universe ฐานมาทำรายงาน


def test_universes_fewer_than_five_rejected():
    with pytest.raises(ValueError):
        run_multiverse_whatif(
            PersonaFactory(),
            n_agents=10,
            max_agents=10,
            universes=3,
            seeds_per_universe=2,
            rounds=10,
            base_messages=[RUMOR],
            event=CORR,
            target_msg_id="rumor",
        )


def test_report_shows_fragility_and_blocks_point_estimate():
    from simulation.experiment import fork_run
    from simulation.report import render_whatif_report

    personas = PersonaFactory().sample(10, seed=1, max_agents=10)
    outcome = fork_run(personas, seed=1, rounds=20, base_messages=[RUMOR], event=CORR)
    est = DeltaEstimate("m", (-0.1, -0.2), -0.15, (-0.2, -0.1))

    fr_ok = FragilityReport(
        universes=(UniverseResult(0, None, est, "ลดลง"),),
        majority_conclusion="ลดลง",
        fragility_index=20,
    )
    report = render_whatif_report(
        title="t",
        estimate=est,
        outcomes=[outcome],
        base_msg_id="rumor",
        event_text="e",
        rounds=20,
        fragility=fr_ok,
    )
    assert "Fragility Index: 20/100" in report
    assert "-15.0%" in report or "−15.0%" in report  # point estimate ยังแสดงได้

    fr_block = FragilityReport(
        universes=(UniverseResult(0, None, est, "ลดลง"),),
        majority_conclusion="ลดลง",
        fragility_index=80,
    )
    blocked = render_whatif_report(
        title="t",
        estimate=est,
        outcomes=[outcome],
        base_msg_id="rumor",
        event_text="e",
        rounds=20,
        fragility=fr_block,
    )
    assert "ตัวเลขเดี่ยวถูกระงับ" in blocked
    assert "**-15.0%**" not in blocked  # ห้าม point estimate เด่นๆ เมื่อ fragility > 70
    assert "คำเตือน (TRUST-05)" in blocked
