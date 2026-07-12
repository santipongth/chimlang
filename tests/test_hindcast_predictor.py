"""tests M4: predictor parsing/majority (fail-closed), truth loader แยกจาก loader, dataset ครบ 5"""

from pathlib import Path

import pytest

from trust.hindcast import load_event
from trust.hindcast.predictor import AgentVote, load_truth, majority, parse_vote

HINDCAST_DIR = Path(__file__).resolve().parents[1] / "data" / "samples" / "hindcast"


def test_parse_vote_valid_fenced_and_garbage():
    v = parse_vote('{"answer": true, "confidence": 0.8, "reason": "โพลนำชัด"}')
    assert v.answer is True and v.confidence == 0.8
    v2 = parse_vote('```json\n{"answer": false, "confidence": 1.5, "reason": "x"}\n```')
    assert v2.answer is False and v2.confidence == 1.0  # clamp
    v3 = parse_vote("ไม่แน่ใจครับ")
    assert v3.answer is None
    v4 = parse_vote('{"answer": "true"}')  # string ไม่ใช่ bool = เสียงเสีย
    assert v4.answer is None


def test_majority_fail_closed_on_tie_or_no_votes():
    yes = AgentVote(True, 0.8, "")
    no = AgentVote(False, 0.8, "")
    bad = AgentVote(None, 0.0, "")
    assert majority([yes, yes, no]) is True
    assert majority([yes, no]) is None  # เสมอ = ตัดสินไม่ได้
    assert majority([bad, bad]) is None  # เสียงเสียหมด = ตัดสินไม่ได้
    assert majority([yes, bad, bad]) is True  # เสียงเสียไม่นับ


def test_all_benchmark_events_load_with_truth():
    event_dirs = sorted(d for d in HINDCAST_DIR.iterdir() if d.is_dir())
    # exit criteria Phase 0 ต้องมี ≥5 — ขยายเป็น 10 เมื่อ 12 ก.ค. 2569 (business goal ≥10 เผยแพร่)
    assert len(event_dirs) >= 10
    for d in event_dirs:
        event = load_event(d)
        truth = load_truth(d)
        assert event.before_docs, f"{d.name}: ไม่มีเอกสาร before ที่ผ่าน filter"
        assert not event.blocked_paths, f"{d.name}: มีเอกสาร before หลัง cutoff"
        for target in event.prediction_targets:
            assert target["id"] in truth, f"{d.name}: target {target['id']} ไม่มีใน truth.yaml"
            assert isinstance(truth[target["id"]], bool)


def test_truth_never_reaches_agent_context():
    # ไฟล์ที่เข้า context agent มีแค่ before/*.md — truth/outcome ต้องไม่ถูก loader แตะ
    from trust.hindcast.prompt import build_hindcast_system_prompt

    for d in sorted(HINDCAST_DIR.iterdir()):
        if not d.is_dir():
            continue
        prompt = build_hindcast_system_prompt(load_event(d))
        assert "truth" not in prompt
        assert "ground truth" not in prompt
        # คำเฉลย binary ต้องไม่โผล่ (สุ่มตรวจคำจาก outcome)
        assert "ห้ามป้อนเข้า simulation" not in prompt


def test_event_passes_requires_all_targets():
    from trust.hindcast.predictor import TargetPrediction, event_passes

    def make(correct: bool) -> TargetPrediction:
        return TargetPrediction(
            target_id="t",
            claim="c",
            votes=(),
            predicted=True,
            truth=True if correct else False,
            correct=correct,
        )

    assert event_passes([make(True), make(True)])
    assert not event_passes([make(True), make(False)])


@pytest.mark.parametrize(
    "event_id", ["2566-general-election", "2566-pm-vote", "2567-digital-wallet-phase1"]
)
def test_new_events_have_pre_cutoff_docs_only(event_id):
    event = load_event(HINDCAST_DIR / event_id)
    assert all(doc.doc_date <= event.cutoff_date for doc in event.before_docs)
