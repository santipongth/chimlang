"""tests P2-M2: ≥3 ตาบังคับ, opponent guardrails, parse fail-closed, society deterministic"""

import pytest

from simulation.game import (
    MIN_TURNS,
    OPPOSITION,
    GameSession,
    GameTurn,
    build_opponent_prompt,
    build_tree_prompt,
    parse_opponent_move,
    parse_tree,
    render_game_report,
    society_react,
)
from simulation.persona import PersonaFactory


class FakeAdapter:
    def chat(self, tier, messages, **kwargs):
        from types import SimpleNamespace

        content = messages[0]["content"]
        if "decision tree" in content:
            return SimpleNamespace(
                text='{"nodes": [{"turn": 1, "taken": "t1", "alternative": "a1"},'
                '{"turn": 2, "taken": "t2", "alternative": "a2"},'
                '{"turn": 3, "taken": "t3", "alternative": "a3"}]}'
            )
        if "private_thought" in content:
            return SimpleNamespace(text='{"private_thought": "คิด", "public_post": "โพสต์"}')
        return SimpleNamespace(text='{"move": "ระดมกลุ่มผู้เสียประโยชน์", "rationale": "ชิงพื้นที่ข่าว"}')


def _session() -> GameSession:
    personas = PersonaFactory().sample(10, seed=1, max_agents=10)
    return GameSession(FakeAdapter(), "แผนทดสอบ", personas, seed=1)


def test_opponent_prompt_guardrails():
    prompt = build_opponent_prompt(OPPOSITION, "แผน", [], "เราเปิดประชาพิจารณ์")
    assert "GOV-05" in prompt and "ห้ามเขียนข้อความหาเสียง" in prompt
    assert "ภาษาไทยเท่านั้น" in prompt and "ห้ามกุตัวเลข" in prompt
    assert "เราเปิดประชาพิจารณ์" in prompt


def test_parse_opponent_move_ok_and_fail_closed():
    move, rat = parse_opponent_move('{"move": "ยื่นศาลปกครอง", "rationale": "ถ่วงเวลา"}')
    assert move == "ยื่นศาลปกครอง" and rat == "ถ่วงเวลา"
    move2, rat2 = parse_opponent_move("ตอบมั่วไม่เป็น JSON")
    assert move2.startswith("ตอบมั่ว") and "parse พัง" in rat2  # การเดินไม่หาย


def test_society_react_deterministic_and_bounded():
    personas = PersonaFactory().sample(10, seed=2, max_agents=10)
    r1 = society_react(personas, "ฝั่งเรา", "ฝั่งค้าน", seed=99)
    r2 = society_react(personas, "ฝั่งเรา", "ฝั่งค้าน", seed=99)
    assert r1 == r2  # deterministic ต่อ seed (NFR-07)
    assert all(0.0 <= x <= 1.0 for x in r1)


def test_game_loop_and_min_turns_enforced():
    session = _session()
    session.play_turn("เดิน 1")
    with pytest.raises(ValueError):
        session.decision_tree()  # < 3 ตา ห้ามสรุป
    session.play_turn("เดิน 2")
    session.play_turn("เดิน 3")
    assert len(session.turns) == MIN_TURNS
    assert session.turns[0].opp_move == "ระดมกลุ่มผู้เสียประโยชน์"
    assert session.turns[0].voices  # มีเสียงชาวเน็ต
    tree = session.decision_tree()
    assert [n.turn_no for n in tree] == [1, 2, 3]
    assert tree[0].alternative == "a1"


def test_parse_tree_fail_closed_keeps_game_data():
    turns = [
        GameTurn(1, "เรา1", "เขา1", "r", 0.6, 0.3, ()),
        GameTurn(2, "เรา2", "เขา2", "r", 0.5, 0.4, ()),
        GameTurn(3, "เรา3", "เขา3", "r", 0.4, 0.5, ()),
    ]
    tree = parse_tree("ไม่เป็น JSON", turns)
    assert len(tree) == 3
    assert "เรา1" in tree[0].taken_summary  # ข้อมูลเกมไม่หายแม้ analyst พัง
    assert "parse พัง" in tree[0].alternative


def test_report_has_tree_and_labels():
    turns = [
        GameTurn(1, "เปิดประชาพิจารณ์", "ยื่นศาล", "ถ่วงเวลา", 0.6, 0.3, ("กลุ่มA: เฉยๆ",)),
        GameTurn(2, "แถลงตัวเลข", "ปล่อยผลโพลค้าน", "ชิงกระแส", 0.5, 0.5, ()),
        GameTurn(3, "ลงพื้นที่", "ระดมม็อบ", "กดดัน", 0.7, 0.2, ()),
    ]
    tree = parse_tree("x", turns)
    report = render_game_report("ทดสอบ", turns, tree)
    assert "simulation_estimate" in report and "GOV-05" in report
    assert "Decision Tree" in report and "ทางเลือก" in report
    assert "เปิดประชาพิจารณ์" in report and "ยื่นศาล" in report
    assert "60%" in report or "0.6" in report  # ตัวเลขความเชื่อปรากฏ
    assert build_tree_prompt("s", turns)  # sanity
