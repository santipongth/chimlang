"""tests สำหรับการแก้รอบ 2: sanitize think tag + judge retry เมื่อ JSON พัง"""

from dataclasses import dataclass
from pathlib import Path

from core.llm import ModelTier
from trust.hindcast import load_event
from trust.hindcast.leaktest import (
    LeakQuestion,
    build_judge_prompt,
    run_leak_test,
    sanitize_answer,
)

ROOT = Path(__file__).resolve().parents[1]
EVENT_DIR = ROOT / "data" / "samples" / "hindcast" / "2565-bkk-governor-election"


def test_sanitize_strips_think_artifacts():
    assert sanitize_answer("<think>คิดในใจ</think>คำตอบจริง") == "คำตอบจริง"
    assert sanitize_answer("</think>\n\nคำตอบจริง") == "คำตอบจริง"
    assert sanitize_answer("คำตอบปกติ") == "คำตอบปกติ"


def test_judge_prompt_contains_calibration_examples():
    event = load_event(EVENT_DIR)
    q = LeakQuestion(id="x", category="direct", prompt="ใครชนะ?", leak_if="ระบุผู้ชนะ")
    p = build_judge_prompt(event, q, "ไม่ทราบครับ")
    assert "อนุมานจากโพล" in p  # few-shot กันตัดสินเข้มเกิน
    assert '"leak"' in p  # ย้ำ key ที่สะกดถูก


@dataclass
class _FakeResult:
    text: str


class _FakeAdapter:
    """crowd ตอบมี think tag; judge ตอบ JSON พังครั้งแรก แล้วถูกครั้งที่สอง"""

    def __init__(self):
        self.judge_calls = 0

    def chat(self, tier, messages, **kwargs):
        if tier == ModelTier.CROWD:
            return _FakeResult(text="</think>ยังไม่ทราบผลครับ")
        self.judge_calls += 1
        if self.judge_calls == 1:
            return _FakeResult(text='{"leark": false, "reason": "typo เหมือนรอบ 1"}')
        return _FakeResult(text='{"leak": false, "reason": "ไม่ leak"}')


def test_judge_retry_on_broken_json():
    event = load_event(EVENT_DIR)
    adapter = _FakeAdapter()
    questions = [LeakQuestion(id="q1", category="direct", prompt="ใครชนะ?", leak_if="-")]

    verdicts = run_leak_test(adapter, event, questions, seed=42)

    assert adapter.judge_calls == 2  # retry เกิดขึ้นจริง
    assert verdicts[0].leak is False  # ผลจากรอบ retry ถูกใช้
    assert verdicts[0].counted_as_leak is False
    assert "</think>" not in verdicts[0].answer  # คำตอบถูก sanitize ก่อนส่ง judge
