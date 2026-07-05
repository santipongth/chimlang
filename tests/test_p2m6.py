"""tests P2-M6: influence segment-only (กฎเหล็กข้อ 7), mutation FAB-04, media FAB-03, waterfall"""

import re

import pytest

from simulation.engine import FabricSimulation, Message
from simulation.influence import (
    build_influence,
    cluster_pairs,
    hub_segments,
    render_influence_section,
)
from simulation.media import STANCES, build_media_prompt, frame_event, parse_headline
from simulation.persona import PersonaFactory


def _run(seed: int = 6, mutation: float = 0.0):
    personas = PersonaFactory().sample(10, seed=seed, max_agents=10)
    sim = FabricSimulation(personas, seed=seed, rumor_mutation_rate=mutation)
    sim.inject(Message("rumor", "rumor", "ข่าวลือ", 1, "public_feed"))
    return sim.run(30)


# --- SIM-09 influence (segment-level only) ---


def test_influence_matrix_segment_level_only():
    result = _run()
    matrix = build_influence(result, "rumor")
    assert matrix.weights, "ควรมีอิทธิพลอย่างน้อยหนึ่งเส้นเมื่อข่าวแพร่"
    segment_names = {s["name"] for s in PersonaFactory().segments}
    for src, dst in matrix.weights:  # ทุก key เป็นชื่อ segment ไม่ใช่ agent id
        assert src in segment_names and dst in segment_names


def test_influence_deterministic_and_hubs_sorted():
    m1 = build_influence(_run(), "rumor")
    m2 = build_influence(_run(), "rumor")
    assert m1.weights == m2.weights
    hubs = hub_segments(m1)
    assert [w for _, w in hubs] == sorted([w for _, w in hubs], reverse=True)


def test_render_has_no_agent_ids():
    """กฎเหล็กข้อ 7: output ห้ามมีตัวระบุระดับบุคคล (agent id pattern เช่น xxx-01)"""
    result = _run()
    section = render_influence_section(build_influence(result, "rumor"), mutation_share=0.1)
    assert "กฎเหล็กข้อ 7" in section or "ห้ามนำไป map" in section
    # agent id เป็นละตินเสมอ (เช่น young_urban-03) — อย่าใช้ \w กว้างๆ เพราะชน "18-30 ปี" ในชื่อกลุ่ม
    agent_id_pattern = re.compile(r"\b[a-z_]+-\d{2}\b")
    assert not agent_id_pattern.search(section)
    assert "10%" in section  # mutation share แสดงผล


def test_cluster_pairs_symmetric_and_capped():
    pairs = cluster_pairs(build_influence(_run(), "rumor"), top=3)
    assert len(pairs) <= 3
    names = [frozenset((a, b)) for a, b, _ in pairs]
    assert len(names) == len(set(names))  # ไม่มีคู่ซ้ำ


# --- FAB-04 rumor mutation ---


def test_mutation_rate_zero_and_full():
    clean = _run(mutation=0.0)
    assert clean.mutation_share("rumor") == 0.0
    full = _run(mutation=1.0)
    # ทุกคนที่ได้ยินผ่าน closed group ต้องได้เวอร์ชันเพี้ยน
    closed_hearers = [
        st for st in full.states.values() if st.heard_via.get("rumor") == "line_closed_group"
    ]
    if closed_hearers:  # ขึ้นกับเส้นทางการแพร่ของ seed นี้
        assert all("rumor" in st.mutated for st in closed_hearers)
    assert any(e["action"] == "heard_mutated" for e in full.trail) == bool(closed_hearers)


def test_mutation_rate_validated():
    personas = PersonaFactory().sample(10, seed=1, max_agents=10)
    with pytest.raises(ValueError):
        FabricSimulation(personas, seed=1, rumor_mutation_rate=1.5)


def test_mutation_deterministic():
    assert _run(mutation=0.5).mutation_share("rumor") == _run(mutation=0.5).mutation_share("rumor")


# --- FAB-03 media agent ---


def test_media_prompt_stances_and_guardrails():
    for stance in STANCES:
        prompt = build_media_prompt("กทม. ประกาศเลื่อนบังคับใช้", stance)
        assert "จำลอง" in prompt and "ไม่ใช่คอนเทนต์เผยแพร่จริง" in prompt
        assert "ภาษาไทยเท่านั้น" in prompt and "ห้ามบิดข้อเท็จจริง" in prompt
    with pytest.raises(ValueError):
        build_media_prompt("x", "propaganda")  # stance นอกลิสต์


def test_parse_headline_ok_and_fallback():
    ok = parse_headline("amplify", '{"headline": "ดราม่าเดือด!"}')
    assert ok.parse_ok and ok.headline == "ดราม่าเดือด!"
    bad = parse_headline("neutral", "ตอบไม่เป็น JSON")
    assert not bad.parse_ok and bad.headline.startswith("ตอบไม่เป็น")  # ไม่ทิ้งข้อมูล


def test_frame_event_uses_fast_mode():
    class FakeAdapter:
        def __init__(self):
            self.kwargs = None

        def chat(self, tier, messages, **kwargs):
            from types import SimpleNamespace

            self.kwargs = kwargs
            return SimpleNamespace(text='{"headline": "h"}')

    fake = FakeAdapter()
    frame_event(fake, "เหตุการณ์", "neutral", seed=1)
    assert fake.kwargs["reasoning"] is False  # โหมดเร็วสำหรับงานสั้น


# --- SIM-10 waterfall (Neo4j — skip ถ้าไม่พร้อม) ---


def test_impact_waterfall_indirect_only():
    from core.config import get_settings
    from graphlayer.store import Neo4jStore
    from graphlayer.waterfall import impact_waterfall, render_waterfall

    try:
        s = get_settings()
        store = Neo4jStore(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
        rows = impact_waterfall(store, "กทม.")
    except Exception:
        pytest.skip("Neo4j ไม่พร้อม (docker compose up -d)")
    assert all(r.hops >= 2 for r in rows)  # เฉพาะผลกระทบทางอ้อม
    if rows:
        assert rows[0].path[0] == "กทม."
        text = render_waterfall("กทม.", rows)
        assert "Impact Waterfall" in text and "provenance" in text
