"""tests P1-M3: provenance cards (TRUST-06), silent majority (TRUST-07), fidelity dial (SIM-06)"""

import pytest

from core.config import Settings
from core.llm import ModelPricing, PricingRegistry
from simulation.engine import FabricSimulation, Message
from simulation.fidelity import PRESETS, PlanBlockedError, ensure_plan_allowed, plan_run
from simulation.persona import PersonaFactory
from simulation.provenance import build_cards, render_provenance_section

# --- TRUST-06 ---


def test_provenance_cards_cover_every_segment():
    cards = build_cards()
    factory = PersonaFactory()
    assert {c.segment_id for c in cards} == {s["id"] for s in factory.segments}
    for c in cards:
        assert c.data_source and c.data_date and c.weighting_method and c.coverage
        assert c.known_bias, f"{c.segment_id}: ไม่มี bias warning — TRUST-06 บังคับให้บอกที่รู้"


def test_provenance_section_shows_bias_warnings():
    section = render_provenance_section(build_cards())
    assert "TRUST-06" in section
    assert "bias ที่ทราบ" in section
    assert "สังเคราะห์" in section  # ต้องบอกตรงๆ ว่ายังเป็นข้อมูลสังเคราะห์


def test_report_includes_provenance_when_given():
    from simulation.experiment import DeltaEstimate, fork_run
    from simulation.report import render_whatif_report

    personas = PersonaFactory().sample(10, seed=1, max_agents=10)
    outcome = fork_run(
        personas,
        seed=1,
        rounds=15,
        base_messages=[Message("rumor", "rumor", "x", 1, "public_feed")],
        event=Message("e", "correction", "y", 5, "public_feed"),
    )
    report = render_whatif_report(
        title="t",
        estimate=DeltaEstimate("m", (-0.1,), -0.1, (-0.2, -0.05)),
        outcomes=[outcome],
        base_msg_id="rumor",
        event_text="e",
        rounds=15,
        provenance_cards=build_cards(),
    )
    assert "Persona Provenance" in report
    assert "silent majority" in report  # TRUST-07 ต้องอยู่ในรายงานเสมอ


# --- TRUST-07 ---


def test_expressors_and_observers_partition():
    personas = PersonaFactory().sample(10, seed=3, max_agents=10)
    sim = FabricSimulation(personas, seed=3)
    sim.inject(Message("rumor", "rumor", "ข่าวลือ", 1, "public_feed"))
    result = sim.run(30)

    expressors, observers = result.expressors(), result.observers()
    assert not (expressors & observers)  # แยกขาดกัน
    heard = {aid for aid, st in result.states.items() if st.heard}
    assert expressors | observers == heard  # ทุกคนที่ได้ยินถูกจัดเข้ากลุ่มใดกลุ่มหนึ่ง
    assert observers, "ควรมี silent majority บ้างตาม voice_activity ของ segments"


# --- SIM-06 ---


@pytest.fixture
def pricing() -> PricingRegistry:
    return PricingRegistry({"test/crowd": ModelPricing(0.065, 0.26)})


def _settings() -> Settings:
    return Settings(llm_model_crowd="test/crowd", llm_model_analyst="test/crowd", _env_file=None)


def test_presets_match_prd():
    assert PRESETS["quick"].agents == 100 and PRESETS["quick"].rounds == 10
    assert PRESETS["standard"].agents == 1000 and PRESETS["standard"].rounds == 30
    assert PRESETS["deep"].agents == 5000 and PRESETS["deep"].rounds == 50
    assert all(p.universes >= 5 for p in PRESETS.values())  # TRUST-04 ทุกระดับ


def test_plan_costs_scale_and_standard_under_target(pricing):
    s = _settings()
    quick = plan_run("quick", s, pricing)
    standard = plan_run("standard", s, pricing)
    deep = plan_run("deep", s, pricing)
    assert quick.est_cost_usd < standard.est_cost_usd < deep.est_cost_usd
    # เป้า NFR-02: standard ≤ $50 ภายใต้สมมติฐาน voice-sparse ที่ calibrate จาก demo จริง
    assert standard.est_cost_usd < 50


def test_cap_policy_after_scale_up(pricing):
    """นโยบาย 6 ก.ค. 2026: dev/quick/standard (≤1,000) รันได้ — deep (5,000) ต้องขอผู้ใช้ก่อน"""
    s = _settings()
    for name in ("dev", "quick", "standard"):
        plan = plan_run(name, s, pricing)
        assert plan.allowed_under_cap, name
        ensure_plan_allowed(plan)  # ไม่ raise
    deep = plan_run("deep", s, pricing)
    assert not deep.allowed_under_cap
    with pytest.raises(PlanBlockedError):
        ensure_plan_allowed(deep)
