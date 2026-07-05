"""tests P2-M1: นักข่าว ≥3 สาย, cap ผู้เข้าร่วม, scorecard parse/fail-closed, GOV-05, report"""

import pytest

from simulation.persona import PersonaFactory
from simulation.rehearsal import (
    JOURNALISTS,
    RehearsalSession,
    Scorecard,
    Turn,
    build_question_prompt,
    build_scorecard_prompt,
    parse_scorecard,
    render_rehearsal_report,
)


class FakeAdapter:
    """ตอบ JSON คงที่ — ใช้ทดสอบ loop โดยไม่เรียก LLM จริง"""

    def chat(self, tier, messages, **kwargs):
        from types import SimpleNamespace

        content = messages[0]["content"]
        if "ที่ปรึกษาการสื่อสาร" in content:
            return SimpleNamespace(
                text='{"calmed": ["c1"], "inflamed": ["i1", "i2"], '
                '"risky_quotes": ["q1"], "summary": "s"}'
            )
        if "private_thought" in content:
            return SimpleNamespace(text='{"private_thought": "คิด", "public_post": "โพสต์"}')
        return SimpleNamespace(text="ถามว่า: งบมาจากไหน?")


def _session(n_netizens: int = 4, max_agents: int = 10) -> RehearsalSession:
    netizens = PersonaFactory().sample(n_netizens, seed=1, max_agents=10)
    return RehearsalSession(FakeAdapter(), "แผนทดสอบ", netizens, seed=1, max_agents=max_agents)


def test_journalists_at_least_three_distinct_styles():
    assert len(JOURNALISTS) >= 3
    assert len({j.role_id for j in JOURNALISTS}) == len(JOURNALISTS)
    ids = {j.role_id for j in JOURNALISTS}
    assert {"political", "economic", "investigative"} <= ids


def test_participants_over_cap_rejected():
    netizens = PersonaFactory().sample(8, seed=1, max_agents=10)
    with pytest.raises(ValueError):  # 3 นักข่าว + 8 ชาวเน็ต = 11 > 10
        RehearsalSession(FakeAdapter(), "s", netizens, seed=1, max_agents=10)


def test_question_prompt_thai_guardrails_and_history():
    prompt = build_question_prompt(JOURNALISTS[0], "แผน", [])
    assert "ภาษาไทยเท่านั้น" in prompt and "ห้ามกุตัวเลข" in prompt
    turn = Turn(1, "นักข่าว", "ถาม?", "ตอบ", (), 1.0)
    prompt2 = build_question_prompt(JOURNALISTS[1], "แผน", [turn])
    assert "ถาม?" in prompt2 and "ตอบ" in prompt2  # transcript ต้องเข้า prompt


def test_scorecard_prompt_has_gov05():
    turn = Turn(1, "นักข่าว", "ถาม?", "ตอบ", (), 1.0)
    prompt = build_scorecard_prompt("แผน", [turn])
    assert "GOV-05" in prompt
    assert "ห้ามร่างคำแถลงใหม่" in prompt  # วิจารณ์ได้ ห้าม ghost-write


def test_parse_scorecard_ok_and_fail_closed():
    ok = parse_scorecard('{"calmed": ["a"], "inflamed": ["b"], "risky_quotes": [], "summary": "x"}')
    assert ok.parse_ok and ok.calmed == ("a",) and ok.inflamed == ("b",)
    bad = parse_scorecard("ประเมินไม่ได้")
    assert not bad.parse_ok
    assert "ประเมินไม่ได้" in bad.summary  # raw ต้องไม่หาย


def test_session_loop_records_turns_and_reactions():
    session = _session()
    role, q, latency = session.next_question()
    assert q  # ได้คำถามจริง
    turn = session.submit_answer(role, q, "คำตอบทดสอบ", latency)
    assert turn.turn_no == 1 and turn.answer == "คำตอบทดสอบ"
    assert turn.reactions  # ชาวเน็ต react (public_post ไม่ว่างจาก fake)
    assert session.turns == [turn]
    # นักข่าวเวียนคนถัดไป
    role2, _, _ = session.next_question()
    assert role2.role_id != role.role_id


def test_scorecard_from_session():
    session = _session()
    role, q, lat = session.next_question()
    session.submit_answer(role, q, "ตอบ", lat)
    card = session.scorecard()
    assert card.parse_ok and card.inflamed == ("i1", "i2")


def test_report_has_latency_target_and_labels():
    turns = [Turn(1, "นักข่าวสายการเมือง", "ถาม?", "ตอบแบบเสี่ยง", ("กลุ่มA: ว้าย",), 3.2)]
    card = Scorecard(("ดับไฟ1",), ("ราดน้ำมัน1",), ("ประโยคเสี่ยง",), "สรุป")
    report = render_rehearsal_report("ทดสอบ", turns, card)
    assert "simulation_estimate" in report and "GOV-05" in report
    assert "≤ 10 วิ: ผ่าน ✅" in report  # latency 3.2 ผ่านเป้า
    assert "ราดน้ำมัน1" in report and "ประโยคเสี่ยง" in report
    assert "ถาม?" in report and "ตอบแบบเสี่ยง" in report  # transcript ครบ
    slow = [Turn(1, "j", "q", "a", (), 12.5)]
    assert "ไม่ผ่าน ❌" in render_rehearsal_report("t", slow, card)
