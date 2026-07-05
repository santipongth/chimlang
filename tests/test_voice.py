from core.text import sanitize_llm_text
from simulation.persona import PersonaFactory
from simulation.voice import build_voice_prompt, parse_voice


def test_sanitize_shared_util():
    assert sanitize_llm_text("<think>x</think>คำตอบ") == "คำตอบ"


def test_voice_prompt_has_guardrails_and_priors():
    p = PersonaFactory().sample(1, seed=1, max_agents=10)[0]
    prompt = build_voice_prompt(p, "ข่าวลือ", believed=True, channel="public_feed")
    assert "ภาษาไทยเท่านั้น" in prompt
    assert "ห้ามกุตัวเลข" in prompt
    assert "private_thought" in prompt and "public_post" in prompt
    assert f"{p.kreng_jai:.1f}" in prompt  # cultural priors ถูกส่งเข้า prompt จริง


def test_parse_voice_valid_and_fallback():
    v = parse_voice("a1", '{"private_thought": "ไม่เชื่อหรอก", "public_post": ""}')
    assert v.private_thought == "ไม่เชื่อหรอก"
    assert v.public_post == ""
    # ตอบไม่เป็น JSON → เก็บดิบเป็นความคิด ไม่ทิ้ง trail และไม่โพสต์
    v2 = parse_voice("a2", "</think>อืม ไม่แน่ใจเลยครับ")
    assert v2.private_thought.startswith("อืม")
    assert v2.public_post == ""
