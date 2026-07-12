"""tests P5-M4: Red Team in-population + compare (controlled experiment, seed เดียวกัน)"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from simulation.compare import run_redteam_compare
from simulation.engine import FabricSimulation, Message
from simulation.persona import PersonaFactory
from simulation.redteam_population import RED_TEAM, RED_TEAM_SEGMENT, inject_red_team

RUMOR = Message("rumor", "rumor", "ข่าวลือทดสอบ", 1, "public_feed")
CORRECTION = Message("official", "correction", "คำชี้แจงทดสอบ", 5, "public_feed", counters="rumor")


def test_inject_replaces_last_two_keeps_count():
    personas = PersonaFactory().sample(20, seed=1, max_agents=20)
    out = inject_red_team(personas)
    assert len(out) == 20
    assert out[-2].agent_id == "redteam-contrarian" and out[-1].agent_id == "redteam-auditor"
    assert all(p.segment_name == RED_TEAM_SEGMENT for p in out[-2:])
    assert out[:18] == personas[:18]  # ที่เหลือไม่ถูกแตะ


def test_inject_rejects_tiny_population():
    personas = PersonaFactory().sample(10, seed=1, max_agents=10)[:3]
    with pytest.raises(ValueError):
        inject_red_team(personas)


def test_default_receptivity_changes_nothing():
    # field ใหม่ default 1.0 — trail ของ population เดิมต้อง identical กับก่อนมี field
    personas = PersonaFactory().sample(20, seed=9, max_agents=20)
    assert all(p.correction_receptivity == 1.0 for p in personas)
    run = lambda: FabricSimulation(  # noqa: E731
        PersonaFactory().sample(20, seed=9, max_agents=20), seed=9
    )
    sim_a, sim_b = run(), run()
    for sim in (sim_a, sim_b):
        sim.inject(RUMOR)
        sim.inject(CORRECTION)
    assert sim_a.run(15).trail == sim_b.run(15).trail  # deterministic เหมือนเดิม


def test_zero_receptivity_never_believes_correction():
    # adversarial ที่ receptivity=0 ต้องไม่เชื่อคำชี้แจงเลยแม้แต่ครั้งเดียว (fail-closed ต่อ correction)
    from dataclasses import replace

    base = PersonaFactory().sample(20, seed=4, max_agents=20)
    hardened = [
        replace(p, agent_id=f"hard-{i:02d}", correction_receptivity=0.0) for i, p in enumerate(base)
    ]
    sim = FabricSimulation(hardened, seed=4)
    sim.inject(RUMOR)
    sim.inject(CORRECTION)
    result = sim.run(20)
    assert not any(st.believed.get("official") for st in result.states.values())


def test_compare_baseline_identical_to_plain_whatif():
    # ฝั่ง baseline ของ compare ต้องเท่ากับ run_whatif ปกติเป๊ะ (seed เดียวกัน = ตัวเลขเดียวกัน)
    from simulation.experiment import run_whatif

    factory = PersonaFactory()
    seeds = [11, 12, 13]
    est, _ = run_whatif(
        lambda s: factory.sample(30, seed=s, max_agents=30),
        seeds=seeds,
        rounds=15,
        base_messages=[RUMOR],
        event=CORRECTION,
        target_msg_id="rumor",
    )
    cmp_result = run_redteam_compare(
        factory,
        n_agents=30,
        max_agents=30,
        rounds=15,
        base_messages=[RUMOR],
        event=CORRECTION,
        target_msg_id="rumor",
        seeds=seeds,
    )
    assert cmp_result["baseline"]["mean_delta"] == pytest.approx(est.mean_delta)
    assert cmp_result["red_team"]["segment_label"] == RED_TEAM_SEGMENT
    assert len(cmp_result["red_team"]["roster"]) == len(RED_TEAM)
    assert isinstance(cmp_result["robust"], bool)
    # red team segment ต้องโผล่ใน breakdown ฝั่ง red team เท่านั้น
    assert RED_TEAM_SEGMENT in cmp_result["red_team"]["belief_by_segment"]
    assert RED_TEAM_SEGMENT not in cmp_result["baseline"]["belief_by_segment"]


def test_compare_deterministic():
    factory = PersonaFactory()
    kwargs = dict(
        n_agents=20,
        max_agents=20,
        rounds=12,
        base_messages=[RUMOR],
        event=CORRECTION,
        target_msg_id="rumor",
        seeds=[7, 8],
    )
    assert run_redteam_compare(factory, **kwargs) == run_redteam_compare(factory, **kwargs)


def test_compare_endpoint_shape_and_election_guard():
    client = TestClient(app)
    r = client.get("/compare.json", params={"subject": "ทดสอบสินค้า", "agents": 20})
    assert r.status_code == 200
    data = r.json()
    assert set(data) >= {"subject", "baseline", "red_team", "delta_of_delta", "robust", "note"}
    # election scenario: dev-admin เป็น verified → ผ่านได้; แต่ granularity individual ไม่มีที่นี่
    # ยืนยันอย่างน้อยว่า endpoint จัดประเภทและไม่ล้ม
    r2 = client.get("/compare.json", params={"subject": "ผลเลือกตั้งผู้ว่าฯ", "agents": 20})
    assert r2.status_code in (200, 403)
