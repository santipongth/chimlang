import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.observability import provider_health, record_provider_call
from core.runstore import RunStore
from scripts.run_phase8_benchmarks import run as run_benchmarks
from simulation.debate import DebatePost
from simulation.debate_protocol import verify_moves
from trust.benchmarks import future_calibration_metrics

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม")


def test_typed_move_verifier_keeps_raw_lineage_and_failures():
    posts = [
        DebatePost(
            0,
            0,
            "แรงงานเมือง",
            "ค่าใช้จ่ายเพิ่ม 25%",
            -0.4,
            -0.2,
            move_id="m1",
            move_type="claim",
        ),
        DebatePost(
            1,
            1,
            "ผู้ค้ารายย่อย",
            "หลักฐานนี้โต้แย้งข้อแรก",
            0.3,
            0.1,
            move_id="m2",
            move_type="evidence",
            parent_move_id="m1",
            evidence_refs=("E404",),
        ),
    ]
    report = verify_moves(posts, evidence_ids={"E1"})
    assert report["status"] == "fail"
    assert report["counts"]["unsupported_numeric_claim"] == 1
    assert report["counts"]["unknown_evidence"] == 1
    assert report["lineage"]["edges"] == [{"from": "m1", "to": "m2", "relation": "evidence"}]


def test_thai_benchmark_suite_reports_all_raw_dimensions():
    report = run_benchmarks()
    assert report["language"] == "th"
    assert report["retrieval"]["sample_size"] == 2
    assert report["retrieval"]["recall_at_k"] > 0
    assert report["evidence"]["unsupported_claims"] == 1
    assert report["subgroup_fidelity"]["mean_absolute_error"] > 0
    assert report["social_desirability"]["direction_accuracy"] == 1
    assert report["future_calibration"]["sample_size"] == 4
    assert "pass" not in report


def test_future_calibration_excludes_unresolved_and_keeps_baseline():
    result = future_calibration_metrics(
        [
            {"probability": 0.8, "outcome": True, "baseline": 0.5},
            {"probability": 0.2, "outcome": False, "baseline": 0.5},
            {"probability": 0.9, "outcome": None, "baseline": 0.5},
        ]
    )
    assert result["sample_size"] == 2
    assert result["brier"] == pytest.approx(0.04)
    assert result["baseline_brier"] == pytest.approx(0.25)


@needs_pg
def test_provider_health_and_prometheus_never_store_prompt_or_response():
    marker = f"test.provider.{uuid4().hex[:8]}"
    record_provider_call(
        DSN,
        run_id="m5-observability-test",
        provider=marker,
        operation="embedding",
        tier="embedding",
        status="success",
        latency_s=0.012,
        input_tokens=12,
        cost_usd=0.0001,
        model_version="embed@test",
    )
    try:
        health = provider_health(DSN)
        row = next(item for item in health["providers"] if item["provider"] == marker)
        assert row["calls"] == 1 and row["success_rate"] == 1
        assert health["pii_policy"] == "metadata_only_no_prompt_or_response"
        response = TestClient(app).get("/metrics")
        assert response.status_code == 200
        assert "chimlang_provider_calls_total" in response.text
        assert "prompt" not in json.dumps(row).lower()
        assert "response" not in json.dumps(row).lower()
    finally:
        import psycopg

        with psycopg.connect(DSN) as conn:
            conn.execute("DELETE FROM provider_call_events WHERE provider = %s", (marker,))


@needs_pg
def test_runstore_roundtrips_typed_move_lineage():
    store = RunStore(DSN)
    run_id = f"m5-moves-{uuid4()}"
    store.create(
        run_id=run_id,
        engine="debate",
        subject="ทดสอบ move lineage",
        domain="ทั่วไป",
        agents=1,
        rounds=1,
        seed=1,
        config={},
    )
    try:
        store.add_posts(
            run_id,
            [
                {
                    "round_no": 0,
                    "agent_idx": 0,
                    "segment": "แรงงานเมือง",
                    "content": "อ้างหลักฐาน",
                    "stance": 0.2,
                    "sentiment": 0,
                    "move_id": "m-r1-a1",
                    "move_type": "evidence",
                    "parent_move_id": "",
                    "evidence_refs": ["E1"],
                }
            ],
        )
        post = store.get(run_id)["posts"][0]
        assert post["move_id"] == "m-r1-a1"
        assert post["move_type"] == "evidence"
        assert post["evidence_refs"] == ["E1"]
    finally:
        store.delete(run_id)
