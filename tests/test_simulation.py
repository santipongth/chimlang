"""tests M3: persona factory (สัดส่วน/cap/reproducibility), engine (determinism/trail/วัฒนธรรม)"""

import pytest

from simulation.channels import CHANNELS
from simulation.engine import FabricSimulation, Message
from simulation.persona import AgentCapExceededError, PersonaFactory


@pytest.fixture(scope="module")
def factory() -> PersonaFactory:
    return PersonaFactory()


def test_allocation_follows_shares(factory):
    counts = factory.allocate(10)
    assert sum(counts.values()) == 10
    # segment ใหญ่สุด (working_commuter 0.22) ต้องได้มากกว่าหรือเท่ากับ segment เล็กสุด (suburban 0.08)
    assert counts["working_commuter"] >= counts["suburban_no_transit"]
    assert counts["working_commuter"] == 2
    # ทุก segment หลักต้องมีตัวแทนอย่างน้อยที่ n=10 พอไหว (เฉพาะ share >= 0.10)
    for sid, c in counts.items():
        share = next(s["share"] for s in factory.segments if s["id"] == sid)
        if share >= 0.10:
            assert c >= 1, f"{sid} (share {share}) ไม่มีตัวแทนเลย"


def test_agent_cap_enforced(factory):
    # คำสั่งผู้ใช้ 5 ก.ค. 2026: ช่วง dev ห้ามเกิน 10 — ต้อง raise ไม่ใช่เตือนเฉยๆ
    with pytest.raises(AgentCapExceededError):
        factory.sample(11, seed=1, max_agents=10)


def test_sampling_reproducible(factory):
    a = factory.sample(10, seed=42, max_agents=10)
    b = factory.sample(10, seed=42, max_agents=10)
    assert a == b  # seed เดิม = persona ชุดเดิมเป๊ะ (NFR-07)
    c = factory.sample(10, seed=43, max_agents=10)
    assert a != c  # seed ต่าง jitter ต้องต่าง


def test_cultural_priors_in_range(factory):
    for p in factory.sample(10, seed=7, max_agents=10):
        for v in (p.kreng_jai, p.say_do_gap, p.sarcasm_meme, p.voice_activity):
            assert 0.0 <= v <= 1.0
        assert abs(sum(p.channel_mix.values()) - 1.0) < 1e-6


def _run(seed: int, rounds: int = 30):
    personas = PersonaFactory().sample(10, seed=seed, max_agents=10)
    sim = FabricSimulation(personas, seed=seed)
    sim.inject(Message("rumor1", "rumor", "ข่าวลือทดสอบ", start_round=1, seed_channel="public_feed"))
    return sim.run(rounds)


def test_engine_deterministic_same_seed():
    r1, r2 = _run(5), _run(5)
    assert r1.trail == r2.trail  # run เดิมทั้ง trail ต้อง reproduce ได้ (NFR-07)
    assert {a: s.heard for a, s in r1.states.items()} == {a: s.heard for a, s in r2.states.items()}


def test_trail_covers_every_hearing_agent():
    result = _run(9)
    heard_agents = {a for a, s in result.states.items() if "rumor1" in s.heard}
    trail_agents = {e["agent"] for e in result.trail if e["action"] == "heard"}
    assert heard_agents == trail_agents  # NFR-08: ทุกเหตุการณ์ย้อนได้จาก trail
    assert heard_agents, "ข่าวลือต้องแพร่ถึงใครสักคนใน 30 rounds"


def test_channel_params_encode_fab01_assumptions():
    # โครงสร้างพารามิเตอร์ต้องสะท้อนสมมติฐาน FAB-01 (ค่าจริงรอ calibrate — FAB-05)
    assert CHANNELS["line_closed_group"].base_rate < CHANNELS["public_feed"].base_rate
    assert CHANNELS["line_closed_group"].trust > CHANNELS["public_feed"].trust
    assert CHANNELS["line_closed_group"].correction_factor < 1.0  # ข่าวแก้เข้ากลุ่มปิดยาก


def test_broadcast_share_reaches_fraction_and_is_deterministic(factory):
    """ADR-0003: broadcast mode (แถลงผ่านสื่อ) ถึง ~share ของประชากรทันที ณ start_round"""
    personas = factory.sample(100, seed=9, max_agents=1000)

    def run(seed):
        sim = FabricSimulation(personas, seed=seed)
        sim.inject(Message("ann", "correction", "แถลง", 1, "public_feed", broadcast_share=0.2))
        return sim.run(1)

    r1, r2 = run(9), run(9)
    heard1 = {a for a, st in r1.states.items() if "ann" in st.heard}
    heard2 = {a for a, st in r2.states.items() if "ann" in st.heard}
    assert heard1 == heard2  # deterministic ต่อ seed
    assert len(heard1) == 20  # 20% ของ 100
    assert not any(e["action"] == "seeded" for e in r1.trail)  # ไม่มี seeder เดี่ยวในโหมดนี้


def test_broadcast_zero_keeps_single_seeder_behavior(factory):
    personas = factory.sample(50, seed=3, max_agents=1000)
    sim = FabricSimulation(personas, seed=3)
    sim.inject(Message("m", "rumor", "x", 1, "public_feed"))
    r = sim.run(1)
    assert sum(1 for e in r.trail if e["action"] == "seeded") == 1  # พฤติกรรมเดิมไม่เปลี่ยน
