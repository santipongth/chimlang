"""Unit tests สำหรับ build_trust_scorecard (ADR-0025)

ครอบบั๊กที่แก้:
- budget check เดิมใช้ payload.get("cost_usd", 0) is not None → pass เสมอแม้ไม่มีข้อมูลต้นทุน
- scorecard ไม่ engine-aware → fabric ($0 กลไก ไม่มี LLM/posts/news) โดน warn จากเช็ค debate
  ทำให้คะแนนต่ำอย่างหลอกๆ
"""

from core.run_quality import build_trust_scorecard

DEBATE_ONLY_CHECK_IDS = {
    "sources",
    "news",
    "parse_failures",
    "budget",
    "deterministic_verifier",
    "analyst_judge",
}


def _debate_detail(**payload_overrides) -> dict:
    payload = {
        "sources": [{"status": "ready"}],
        "news": {"items": [{"status": "ready"}]},
        "metrics": {"posts_ok": 10, "posts_failed": 0},
        "cost_usd": 0.01,
        "protocol": {
            "verifier": {"status": "pass", "violations": []},
            "analyst_judge": {"verdict": "pass"},
        },
    }
    payload.update(payload_overrides)
    return {
        "engine": "debate",
        "status": "complete",
        "payload": payload,
        "manifest": {},  # legacy → reproducibility = warn
    }


def _check(card: dict, check_id: str) -> dict:
    return next(c for c in card["checks"] if c["id"] == check_id)


def test_budget_check_warns_when_cost_data_missing():
    """บั๊กเดิม: ไม่มี cost_usd ใน payload ต้อง warn ไม่ใช่ pass."""
    detail = _debate_detail()
    del detail["payload"]["cost_usd"]
    card = build_trust_scorecard(detail)
    assert _check(card, "budget")["status"] == "warn"


def test_budget_check_passes_when_cost_recorded_even_zero():
    card = build_trust_scorecard(_debate_detail(cost_usd=0.0))
    assert _check(card, "budget")["status"] == "pass"


def test_fabric_scorecard_excludes_debate_only_checks():
    """fabric (กลไก $0) ต้องไม่โดนหักคะแนนจากเช็ค sources/news/posts/budget/verifier/judge."""
    detail = {
        "engine": "fabric",
        "status": "complete",
        "payload": {"brief": {"fragility_index": 10}},
        "manifest": {},
    }
    card = build_trust_scorecard(detail)
    check_ids = {c["id"] for c in card["checks"]}
    assert check_ids == {"status", "reproducibility"}
    assert not (check_ids & DEBATE_ONLY_CHECK_IDS)
    # สูตรคะแนน: status pass (w=2) + reproducibility warn (w=1) → (2 + 0.5)/3 = 83
    assert sum(c["weight"] for c in card["checks"]) == 3
    assert card["score"] == 83
    assert card["band"] == "usable"


def test_debate_scorecard_keeps_full_check_set():
    card = build_trust_scorecard(_debate_detail())
    check_ids = {c["id"] for c in card["checks"]}
    assert check_ids == {"status", "reproducibility"} | DEBATE_ONLY_CHECK_IDS
    # ทุกเช็ค pass ยกเว้น reproducibility (legacy manifest) warn:
    # earned = 11 + 0.5, total = 12 → 96 strong
    assert sum(c["weight"] for c in card["checks"]) == 12
    assert card["score"] == 96
    assert card["band"] == "strong"


def test_unknown_engine_keeps_full_check_set_conservatively():
    detail = _debate_detail()
    detail["engine"] = "mystery-engine"
    card = build_trust_scorecard(detail)
    check_ids = {c["id"] for c in card["checks"]}
    assert DEBATE_ONLY_CHECK_IDS <= check_ids


def test_score_denominator_matches_emitted_checks():
    """total_weight ต้องมาจาก checks ที่ append จริงเท่านั้น (ข้อ c ของ review)."""
    for detail in (
        _debate_detail(),
        {"engine": "fabric", "status": "queued", "payload": {}, "manifest": {}},
    ):
        card = build_trust_scorecard(detail)
        total = sum(c["weight"] for c in card["checks"])
        earned = sum(c["weight"] for c in card["checks"] if c["status"] == "pass") + 0.5 * sum(
            c["weight"] for c in card["checks"] if c["status"] == "warn"
        )
        assert card["score"] == round(100 * earned / max(1, total))
