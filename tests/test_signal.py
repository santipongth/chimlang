"""tests P2-M4: features+CI, metadata บังคับ (SIG-03), OOS harness (SIG-02), GOV-02/429 ที่ API"""

import pytest
from fastapi.testclient import TestClient

import api.app as api_app
from simulation.engine import FabricSimulation, Message
from simulation.persona import DEFAULT_SEGMENTS_PATH, PersonaFactory
from trust.signal import DISCLAIMER, build_signal_bundle, features_for_run
from trust.signal_harness import (
    SampleTooSmallError,
    evaluate,
    hit_rate,
    information_coefficient,
    train_test_split_chrono,
)
from trust.universe import FragilityReport


def _run(seed: int):
    personas = PersonaFactory().sample(10, seed=seed, max_agents=10)
    sim = FabricSimulation(personas, seed=seed)
    sim.inject(Message("rumor", "rumor", "ข่าวลือ", 1, "public_feed"))
    return sim.run(20)


def _fragility(index: int = 20) -> FragilityReport:
    return FragilityReport(universes=(), majority_conclusion="ลดลง", fragility_index=index)


# --- SIG-01/03/04 ---


def test_features_bounded_and_deterministic():
    f1 = features_for_run(_run(7), "rumor", rounds=20)
    f2 = features_for_run(_run(7), "rumor", rounds=20)
    assert f1 == f2  # deterministic ต่อ seed
    for name, v in f1.items():
        assert -1.0 <= v <= 1.0, name
    assert set(f1) == {
        "narrative_momentum",
        "narrative_dispersion",
        "sentiment_divergence",
        "contrarian_pressure",
        "adoption_elasticity",
    }


def test_bundle_metadata_and_disclaimer_mandatory():
    bundle = build_signal_bundle(
        [_run(1), _run(2), _run(3)],
        "rumor",
        rounds=20,
        fragility=_fragility(35),
        run_id="signal-test",
        calibration_note="n/a",
        model_version="test@1",
        provenance_source=DEFAULT_SEGMENTS_PATH,
    )
    d = bundle.to_dict()
    md = d["metadata"]  # SIG-03: ครบทุก field
    assert md["run_id"] == "signal-test" and md["fragility_index"] == 35
    assert md["provenance_hash"] and md["model_version"] == "test@1"
    assert d["disclaimer"] == DISCLAIMER  # SIG-04: เชิงโครงสร้าง
    names = {f["name"] for f in d["features"]}
    assert "consensus_fragility" in names
    for f in d["features"]:
        assert len(f["ci95"]) == 2  # ทุก feature มีช่วงเสมอ (TRUST-09)


# --- SIG-02 harness ---


def test_split_is_chronological_no_leakage():
    xs = list(range(20))
    x_train, y_train, x_test, y_test = train_test_split_chrono(xs, xs)
    assert max(x_train) < min(x_test)  # test อยู่อนาคตของ train เสมอ
    assert len(x_test) == 6


def test_small_test_set_refused():
    with pytest.raises(SampleTooSmallError):
        train_test_split_chrono([1.0] * 8, [1.0] * 8)  # test = 2 จุด < 5


def test_ic_perfect_and_inverse_and_flat():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert information_coefficient(xs, [10, 20, 30, 40, 50]) == pytest.approx(1.0)
    assert information_coefficient(xs, [50, 40, 30, 20, 10]) == pytest.approx(-1.0)
    assert information_coefficient(xs, [7, 7, 7, 7, 7]) == 0.0


def test_evaluate_predictive_feature_beats_baseline():
    # feature ทำนายทิศ target ได้จริง (สลับขึ้นลงตาม feature) — baseline ทายข้างมากทางเดียว
    feature = [0.1, 0.9, 0.2, 0.8, 0.1, 0.9, 0.2, 0.8, 0.1, 0.9, 0.2, 0.8, 0.1, 0.9, 0.2, 0.8]
    target = [-1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 1.0]
    report = evaluate(feature, target)
    assert report.n_test >= 5 and report.improves_over_baseline
    # ic ~0.89 (ไม่ถึง 1 เพราะ tie ใน feature ลดอันดับ Spearman — พฤติกรรมถูกต้องของสูตร)
    assert report.hit_rate_test == 1.0 and report.ic_test > 0.8


def test_evaluate_random_feature_does_not_improve():
    feature = [0.5, 0.1, 0.9, 0.4, 0.6, 0.2, 0.8, 0.3, 0.7, 0.5, 0.1, 0.9, 0.4, 0.6, 0.2, 0.8]
    target = [1.0] * 16  # target ขึ้นตลอด — baseline (ข้างมาก=ขึ้น) ควรชนะ feature มั่ว
    report = evaluate(feature, target)
    assert not report.improves_over_baseline
    assert report.baseline_hit_rate == 1.0


def test_hit_rate_bounds():
    assert 0.0 <= hit_rate([1, 2, 3, 4.0], [1, -1, 1, -1.0]) <= 1.0


# --- API (GOV-02 + rate limit) ---


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(api_app.app)


def test_signal_endpoint_returns_features_with_metadata(client):
    r = client.get("/signal.json", params={"subject": "แคมเปญราคาสินค้า"})
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["run_id"].startswith("signal-")
    assert "disclaimer" in body and body["features"]


def test_signal_blocked_for_election_scenario(client):
    r = client.get("/signal.json", params={"subject": "จำลองผลเลือกตั้งผู้ว่าฯ"})
    assert r.status_code == 403  # GOV-02: Sim-to-Signal ปิดใน election mode
    assert "Sim-to-Signal" in r.json()["detail"]


def test_signal_rate_limited(client, monkeypatch):
    monkeypatch.setattr(api_app, "signal_rate_limiter", api_app.RateLimiter(1, 60.0))
    assert client.get("/signal.json").status_code == 200
    assert client.get("/signal.json").status_code == 429


def test_oos_endpoint_rejects_small_sample(client):
    r = client.post(
        "/signal/oos-test.json", json={"feature_series": [1, 2, 3], "target_series": [1, 2, 3]}
    )
    assert r.status_code == 422  # เล็กเกิน — ปฏิเสธการสรุป (fail-closed)


def test_oos_endpoint_full_flow(client):
    feature = [0.1, 0.9] * 8
    target = [-1.0, 1.0] * 8
    r = client.post(
        "/signal/oos-test.json", json={"feature_series": feature, "target_series": target}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["improves_over_baseline"] is True
    assert "ห้าม shuffle" in body["note"]
