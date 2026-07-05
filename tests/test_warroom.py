"""tests P2-M3: SIM-11 gate (hindcast block), PII block ใน feed, envelope deterministic, alarm"""

from datetime import date

import pytest

from core.run_context import ExternalRetrievalBlockedError, RunContext
from governance.pii import PIIDetector
from simulation.engine import FabricSimulation, Message
from simulation.persona import PersonaFactory
from simulation.warroom import (
    DIVERGENCE_TOLERANCE,
    FeedBlockedError,
    Forecast,
    Observation,
    check_divergence,
    forecast_48h,
    load_feed,
    render_warroom_report,
)

LIVE_CTX = RunContext(run_id="t", seed=1)
HINDCAST_CTX = RunContext(run_id="t", seed=1, hindcast_mode=True, cutoff_date=date(2023, 1, 1))


def _write_feed(tmp_path, note: str = "aggregate ปกติ"):
    p = tmp_path / "feed.yaml"
    p.write_text(
        "observations:\n"
        f'  - {{t_hour: 0, metric: belief_share, value: 0.3, note: "{note}"}}\n'
        "  - {t_hour: 12, metric: belief_share, value: 0.4}\n",
        encoding="utf-8",
    )
    return p


def test_sim11_gate_blocks_hindcast_mode(tmp_path):
    """กฎเหล็กข้อ 2: war room feed = external retrieval — hindcast ต้อง block ตาย"""
    p = _write_feed(tmp_path)
    load_feed(p, LIVE_CTX, PIIDetector())  # live ผ่าน
    with pytest.raises(ExternalRetrievalBlockedError):
        load_feed(p, HINDCAST_CTX, PIIDetector())


def test_feed_with_pii_note_blocked(tmp_path):
    p = _write_feed(tmp_path, note="พบโพสต์จากเบอร์ 081-234-5678 โทรกลับด้วย")
    with pytest.raises(FeedBlockedError):
        load_feed(p, LIVE_CTX, PIIDetector())


def test_feed_value_out_of_range_blocked(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text(
        "observations:\n  - {t_hour: 0, metric: belief_share, value: 1.7}\n", encoding="utf-8"
    )
    with pytest.raises(FeedBlockedError):
        load_feed(p, LIVE_CTX, PIIDetector())


def test_preseed_sets_belief_share_and_rejects_wrong_round():
    personas = PersonaFactory().sample(10, seed=3, max_agents=10)
    sim = FabricSimulation(personas, seed=3)
    ids = {p.agent_id for p in personas[:4]}
    sim.preseed(Message("n", "rumor", "x", 0, "public_feed"), ids)
    result = sim.run(1)
    believed = {a for a, st in result.states.items() if st.believed.get("n")}
    assert ids <= believed  # ผู้ preseed เชื่อครบ
    with pytest.raises(ValueError):
        FabricSimulation(personas, seed=3).preseed(
            Message("m", "rumor", "x", 1, "public_feed"), ids
        )


def test_forecast_envelope_deterministic_and_ordered():
    personas = PersonaFactory().sample(10, seed=5, max_agents=10)
    obs = Observation(t_hour=0, metric="belief_share", value=0.3)
    f1 = forecast_48h(personas, "n", obs, base_seed=42)
    f2 = forecast_48h(personas, "n", obs, base_seed=42)
    assert f1.envelope == f2.envelope  # deterministic (NFR-07)
    assert len(f1.envelope) == 12  # 48 ชม. / 4 ชม.ต่อ round
    for lo, hi in f1.envelope:
        assert 0.0 <= lo <= hi <= 1.0
    # share เริ่ม 0.3 — envelope ไม่ควรต่ำกว่าจุดตั้งต้น (belief สะสมไม่ลดในโมเดลนี้)
    assert f1.envelope[0][0] >= 0.3 - 1e-9


def test_divergence_inside_and_outside():
    fc = Forecast(made_at_hour=0, base_value=0.3, envelope=tuple([(0.3, 0.6)] * 12))
    inside = check_divergence(fc, Observation(12, "belief_share", 0.5))
    assert inside.score == 0.0 and not inside.alarm
    outside = check_divergence(fc, Observation(12, "belief_share", 0.95))
    assert outside.score == pytest.approx(0.35) and outside.alarm
    beyond = check_divergence(fc, Observation(120, "belief_share", 0.95))
    assert beyond.bounds is None and not beyond.alarm  # เกินขอบฟ้า — ไม่ตัดสิน


def test_tolerance_absorbs_tiny_noise():
    fc = Forecast(made_at_hour=0, base_value=0.3, envelope=tuple([(0.3, 0.6)] * 12))
    tiny = check_divergence(fc, Observation(12, "belief_share", 0.6 + DIVERGENCE_TOLERANCE / 2))
    assert not tiny.alarm


def test_report_shows_alarm_banner_only_when_diverged():
    fc = Forecast(made_at_hour=0, base_value=0.3, envelope=tuple([(0.3, 0.6)] * 12))
    ok = check_divergence(fc, Observation(12, "belief_share", 0.5))
    bad = check_divergence(fc, Observation(24, "belief_share", 0.95))
    calm = render_warroom_report("t", "n", [fc], [ok])
    assert "DIVERGENCE ALARM" not in calm and "simulation_estimate" in calm
    alarmed = render_warroom_report("t", "n", [fc], [ok, bad])
    assert "DIVERGENCE ALARM" in alarmed and "ยังไม่ถูก model" in alarmed
