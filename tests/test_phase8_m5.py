import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.config import Settings
from core.llm.adapter import EmbeddingResult, LLMAdapter
from core.llm.cost import BudgetExceededError, BudgetGuard
from core.llm.pricing import ModelPricing, PricingRegistry
from core.observability import provider_health, record_provider_call
from core.runstore import RunStore
from scripts.run_phase8_benchmarks import run as run_benchmarks
from simulation.debate import DebatePost
from simulation.debate_protocol import verify_moves
from simulation.reflection import ReflectionPolicy, reflection_benchmark
from simulation.sources import index_run_embeddings, ingest_sources, retrieve_evidence
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


def test_reflection_benchmark_reports_bounds_without_inventing_pass_gate():
    policy = ReflectionPolicy(max_calls=2, max_input_chars=1200, max_output_tokens=160)
    report = reflection_benchmark(
        {"severity": {"error": 2, "warning": 3}},
        {"severity": {"error": 1, "warning": 4}},
        calls=2,
        policy=policy,
    )
    assert report["error_delta"] == -1
    assert report["warning_delta"] == 1
    assert report["within_call_bound"] is True
    assert "passed" not in report


class _Embeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        vectors = [[1.0] + [0.0] * 127 for _ in kwargs["input"]]
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=vector) for vector in vectors],
            usage=SimpleNamespace(prompt_tokens=10, total_tokens=10),
            model=kwargs["model"] + "@snapshot",
        )


def test_embedding_adapter_is_priced_and_guarded_before_provider_call(monkeypatch):
    monkeypatch.setattr("core.llm.adapter.record_provider_call", lambda *args, **kwargs: None)
    spend_rows = []
    monkeypatch.setattr(
        "core.llm.adapter.record_spend",
        lambda dsn, usd, run_id="", **kwargs: spend_rows.append((usd, run_id)),
    )
    embeddings = _Embeddings()
    client = SimpleNamespace(embeddings=embeddings, chat=SimpleNamespace(completions=None))
    settings = Settings(
        llm_base_url="https://example.invalid/v1",
        llm_api_key="test",
        llm_model_crowd="crowd",
        llm_model_analyst="analyst",
        llm_model_embedding="embed",
        llm_embedding_dimension=128,
        postgres_url="postgresql://invalid:invalid@127.0.0.1:1/invalid",
        _env_file=None,
    )
    pricing = PricingRegistry(
        {
            "crowd": ModelPricing(1, 1),
            "analyst": ModelPricing(1, 1),
            "embed": ModelPricing(1, 0),
        }
    )
    adapter = LLMAdapter(
        settings, pricing, BudgetGuard(1), client=client, run_id="m5-embedding-ledger"
    )
    result = adapter.embed(["หลักฐานภาษาไทย"])
    assert result.dimension == 128 and result.model.endswith("@snapshot")
    assert result.cost_usd == pytest.approx(0.00001)
    assert embeddings.calls[0]["dimensions"] == 128
    assert spend_rows == [(pytest.approx(0.00001), "m5-embedding-ledger")]

    blocked = LLMAdapter(settings, pricing, BudgetGuard(0.000001), client=client)
    with pytest.raises(BudgetExceededError) as exc:
        blocked.embed(["ข้อความยาวกว่างบ"])
    assert exc.value.phase == "pre_call"
    assert len(embeddings.calls) == 1
    assert len(spend_rows) == 1


class _DeterministicEmbeddingAdapter:
    embedding_model = "test/thai-embed"
    embedding_dimension = 1536

    def supports_embeddings(self):
        return True

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * 1536
            if "รถติด" in text or "congestion" in text:
                vector[0] = 1.0
            else:
                vector[1] = 1.0
            vectors.append(tuple(vector))
        return EmbeddingResult(tuple(vectors), "test/thai-embed@v1", 1536, 10, 0.0)


@needs_pg
def test_pgvector_hnsw_and_bm25_are_fused_with_rrf():
    run_id = f"m5-vector-{uuid4()}"
    ingest_sources(
        DSN,
        run_id,
        [
            {
                "kind": "text",
                "label": "ค่ารถติด",
                "text": "มาตรการค่าธรรมเนียมรถติดกระทบผู้ค้ารายย่อยและการเดินทาง " * 30,
            },
            {
                "kind": "text",
                "label": "เกษตร",
                "text": "ราคาปุ๋ยและผลผลิตข้าวของเกษตรกร " * 30,
            },
        ],
    )
    adapter = _DeterministicEmbeddingAdapter()
    try:
        indexed = index_run_embeddings(DSN, run_id, adapter)
        result = retrieve_evidence(
            DSN,
            run_id,
            "รถติดผู้ค้ารายย่อย",
            mode="hybrid",
            embedding_adapter=adapter,
        )
        assert indexed["index"] == "pgvector_hnsw" and indexed["indexed"] >= 2
        assert result[0]["retrieval_mode"] == "rrf_pgvector_bm25"
        assert result[0]["embedding_provenance"]["model_version"].endswith("@v1")
        assert result[0]["rank_components"]["vector_rank"] == 1
        assert result[0]["note"] == ""
        import psycopg

        with psycopg.connect(DSN) as conn:
            conn.execute(
                "DELETE FROM run_chunk_embeddings WHERE chunk_id = ("
                "SELECT chunk_id FROM run_chunk_embeddings WHERE run_id = %s LIMIT 1)",
                (run_id,),
            )
        fallback = retrieve_evidence(
            DSN,
            run_id,
            "รถติดผู้ค้ารายย่อย",
            mode="hybrid",
            embedding_adapter=adapter,
        )
        assert fallback[0]["retrieval_mode"] == "bm25_fallback_embedding_unavailable"
        assert fallback[0]["embedding_provenance"]["reason"] == "embedding_coverage_incomplete"
    finally:
        import psycopg

        with psycopg.connect(DSN) as conn:
            conn.execute("DELETE FROM run_sources WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM run_chunks WHERE run_id = %s", (run_id,))


def test_thai_benchmark_suite_reports_all_raw_dimensions():
    report = run_benchmarks()
    assert report["language"] == "th"
    assert report["retrieval"]["sample_size"] == 2
    assert report["retrieval"]["recall_at_k"] > 0
    assert report["evidence"]["unsupported_claims"] == 1
    assert report["subgroup_fidelity"]["mean_absolute_error"] > 0
    assert report["social_desirability"]["direction_accuracy"] == 1
    assert report["future_calibration"]["sample_size"] == 4
    assert report["reflection_smoke"]["within_call_bound"] is True
    assert report["reflection_smoke"]["error_delta"] < 0
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
