"""tests P2-M5: memory roundtrip/isolation/reset (DB จริง), PII block, ask cite trail จริง"""

import pytest

from governance.pii import PIIDetector
from simulation.ask import build_ask_prompt, parse_answer, render_answer, select_trail
from simulation.engine import FabricSimulation, Message
from simulation.memory import MemoryBlockedError, WorldMemory, render_memory_context
from simulation.persona import PersonaFactory

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"
WS = "test-living-world"


@pytest.fixture(scope="module")
def memory() -> WorldMemory:
    m = WorldMemory(DSN, PIIDetector())
    try:
        m.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    m.reset_world(WS)
    m.reset_world(WS + "-other")
    return m


def _run(seed: int = 4):
    personas = PersonaFactory().sample(10, seed=seed, max_agents=10)
    sim = FabricSimulation(personas, seed=seed)
    sim.inject(Message("rumor", "rumor", "ข่าวลือ", 1, "public_feed"))
    return sim.run(20)


# --- SIM-05 memory ---


def test_remember_recall_and_latest_belief(memory):
    memory.remember(WS, "real_event", "กทม. แถลงเลื่อนบังคับใช้")
    memory.remember(WS, "sim_result", "run A: เชื่อ 40%", belief_share=0.4, source_run_id="A")
    memory.remember(WS, "sim_result", "run B: เชื่อ 60%", belief_share=0.6, source_run_id="B")
    items = memory.recall(WS)
    assert len(items) == 3
    assert items[0].source_run_id == "B"  # ใหม่สุดก่อน
    assert memory.latest_belief(WS) == 0.6  # สถานะล่าสุดของโลก


def test_workspace_isolation(memory):
    memory.remember(WS + "-other", "user_note", "โลกอื่น")
    assert all(m.content != "โลกอื่น" for m in memory.recall(WS))


def test_pii_in_memory_blocked(memory):
    with pytest.raises(MemoryBlockedError):
        memory.remember(WS, "user_note", "ติดต่อคุณสมชาย ใจดี ที่ 081-234-5678")
    # ต้องไม่ถูกบันทึก
    assert all("081" not in m.content for m in memory.recall(WS))


def test_reset_world_clears_only_own_workspace(memory):
    removed = memory.reset_world(WS)
    assert removed >= 3
    assert memory.recall(WS) == []
    assert memory.recall(WS + "-other")  # โลกอื่นไม่โดนล้าง


def test_render_memory_context_empty_and_filled(memory):
    assert "ยังไม่มีความจำ" in render_memory_context([])
    memory.remember(WS, "real_event", "เหตุการณ์ทดสอบ")
    text = render_memory_context(memory.recall(WS))
    assert "เหตุการณ์จริง" in text and "เหตุการณ์ทดสอบ" in text


# --- SIM-08 ask ---


def test_select_trail_filters_and_caps():
    result = _run()
    all_events = select_trail(result)
    assert 0 < len(all_events) <= 80
    seg = next(iter({st.persona.segment_name for st in result.states.values()}))
    seg_events = select_trail(result, segment=seg)
    seg_agents = {a for a, st in result.states.items() if st.persona.segment_name == seg}
    assert all(e["agent"] in seg_agents for e in seg_events)


def test_ask_prompt_forbids_outside_knowledge():
    events = select_trail(_run())
    prompt = build_ask_prompt("ทำไมเชื่อ", events)
    assert "เท่านั้น" in prompt and "ห้ามใช้ความรู้ภายนอก" in prompt
    assert "[0]" in prompt  # เหตุการณ์มีเลขอ้างอิง


def test_parse_answer_validates_citations():
    events = select_trail(_run())[:5]
    good = parse_answer("q", '{"answer": "เพราะ [0] และ [2]", "cited_events": [0, 2]}', events)
    assert good.grounded and len(good.cited_events) == 2
    # อ้าง index มั่ว (999) = ตัดทิ้ง → เหลือ citation จริงเท่านั้น
    partial = parse_answer("q", '{"answer": "x", "cited_events": [0, 999]}', events)
    assert len(partial.cited_events) == 1
    # ไม่มี citation เลย = ไม่ grounded (ติดธงเตือน)
    empty = parse_answer("q", '{"answer": "ตอบลอยๆ", "cited_events": []}', events)
    assert not empty.grounded
    assert "อย่าใช้คำตอบนี้ตัดสินใจ" in render_answer(empty)


def test_parse_answer_garbage_fail_closed():
    events = select_trail(_run())[:3]
    ta = parse_answer("q", "ตอบไม่เป็น JSON เลย", events)
    assert not ta.grounded and ta.answer.startswith("ตอบไม่เป็น")
