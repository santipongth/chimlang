from datetime import date
from pathlib import Path

from trust.hindcast import build_hindcast_system_prompt, load_event
from trust.hindcast.leaktest import LeakQuestion, load_questions, parse_judge

ROOT = Path(__file__).resolve().parents[1]
EVENT_DIR = ROOT / "data" / "samples" / "hindcast" / "2565-bkk-governor-election"
QUESTIONS = ROOT / "data" / "benchmark" / "leak_questions_2565_bkk_election.yaml"


def test_load_real_event():
    event = load_event(EVENT_DIR)
    assert event.cutoff_date == date(2022, 5, 20)
    assert len(event.before_docs) == 3
    assert not event.blocked_paths  # เอกสาร before ทุกไฟล์ต้องลงวันที่ก่อน cutoff
    assert all(doc.doc_date <= event.cutoff_date for doc in event.before_docs)
    # outcome.md (ground truth) ต้องไม่ถูกโหลดเข้า context เด็ดขาด
    assert all("outcome" not in doc.path.name for doc in event.before_docs)


def test_system_prompt_contains_guardrails_not_outcome():
    event = load_event(EVENT_DIR)
    prompt = build_hindcast_system_prompt(event)
    assert "20 พฤษภาคม พ.ศ. 2565" in prompt  # ตรึงวันที่
    assert "ภาษาไทยเท่านั้น" in prompt
    # กันการรั่วจากตัว prompt เอง: ห้ามมีตัวเลขผลจริงหลุดเข้ามา
    assert "1,386,215" not in prompt
    assert "1.38" not in prompt


def test_question_set_meets_m1_requirements():
    questions = load_questions(QUESTIONS)
    assert len(questions) >= 30  # AC ของ M1: ≥ 30 ข้อ
    assert all(isinstance(q, LeakQuestion) and q.leak_if for q in questions)
    assert len({q.category for q in questions}) >= 5  # หลากหลายกลยุทธ์โจมตี


def test_judge_parse_valid_and_fenced():
    leak, reason = parse_judge('{"leak": true, "reason": "อ้างผลจริง"}')
    assert leak is True and reason == "อ้างผลจริง"
    leak, _ = parse_judge('```json\n{"leak": false, "reason": "คาดเดาจากโพล"}\n```')
    assert leak is False


def test_judge_parse_garbage_is_conservative():
    # judge ตอบไม่เป็น JSON → None → counted_as_leak ต้องเป็น True (fail-closed)
    from trust.hindcast.leaktest import LeakVerdict

    leak, reason = parse_judge("ผมคิดว่าไม่ leak นะครับ")
    assert leak is None
    v = LeakVerdict(
        question=LeakQuestion(id="x", category="direct", prompt="?", leak_if="-"),
        answer="-",
        leak=leak,
        reason=reason,
    )
    assert v.counted_as_leak is True


def test_judge_parse_non_bool_leak():
    leak, _ = parse_judge('{"leak": "maybe", "reason": "?"}')
    assert leak is None
