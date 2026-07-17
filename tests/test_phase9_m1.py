import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import app
from core.run_manifest import (
    build_manifest,
    build_run_spec,
    canonical_hash,
    verify_manifest_hash,
)
from core.runstore import RunCanceledError, RunStore
from core.safe_fetch import (
    DEFAULT_CONTENT_TYPES,
    SafeFetchError,
    SafeFetchResponse,
    SafeOutboundFetcher,
    _PinnedBackend,
)
from core.tasks import celery_app

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม")


@pytest.fixture
def client():
    old_eager = celery_app.conf.task_always_eager
    old_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    with TestClient(app) as test_client:
        yield test_client
    celery_app.conf.task_always_eager = old_eager
    celery_app.conf.task_eager_propagates = old_propagates


def _complete_versions(engine: str = "fabric") -> dict:
    return {
        "git": "abc123",
        "engine": {"name": engine, "files": {"engine.py": "a" * 64}},
        "adapter": {"source_hash": "b" * 64},
        "prompts": {"source_hash": "c" * 64},
        "model": {"provider": "none", "models": {}},
    }


def test_manifest_hash_is_canonical_and_input_snapshots_are_isolated():
    request = {"subject": "นโยบายทดสอบ", "sources": [{"kind": "text", "text": "หลักฐาน"}]}
    population = [{"id": "a", "share": 1.0, "traits": ["ระวังความเสี่ยง"]}]
    spec = build_run_spec(request, seed=17, population_segments=population)
    original_hash = canonical_hash(spec)

    request["sources"][0]["text"] = "ถูกแก้ภายหลัง"
    population[0]["share"] = 0.5

    assert canonical_hash(spec) == original_hash
    assert spec.request["sources"][0]["text"] == "หลักฐาน"
    assert spec.population_snapshot["segments"][0]["share"] == 1.0
    assert canonical_hash({"ข": 2, "ก": 1}) == canonical_hash({"ก": 1, "ข": 2})


def test_complete_manifest_verifies_and_tampering_fails():
    spec = build_run_spec(
        {"engine": "fabric", "subject": "นโยบายทดสอบ"},
        seed=2,
        population_segments=[{"id": "all", "share": 1.0}],
    )
    manifest = build_manifest(
        run_id="fabric-test",
        status="complete",
        spec=spec,
        versions=_complete_versions(),
        pricing={},
        governance={"pii_detector": "passed"},
        snapshots={"evidence": [], "news": [], "posts": [], "result": {"value": 1}},
    ).model_dump(mode="json")

    assert manifest["complete"] is True
    assert manifest["reproducibility"] == "frozen-inputs-best-effort"
    assert verify_manifest_hash(manifest) is True
    manifest["snapshots"]["result"]["value"] = 2
    assert verify_manifest_hash(manifest) is False


def test_manifest_stays_incomplete_when_required_versions_are_missing():
    spec = build_run_spec(
        {"engine": "fabric", "subject": "ทดสอบ manifest ไม่ครบ"},
        seed=1,
        population_segments=[{"id": "all", "share": 1.0}],
    )
    manifest = build_manifest(
        run_id="fabric-incomplete",
        status="complete",
        spec=spec,
        versions={"git": "unknown"},
        pricing={},
        governance={"pii_detector": "passed"},
        snapshots={"evidence": [], "news": [], "posts": [], "result": {"ok": True}},
    )
    assert manifest.complete is False
    assert "git-version-missing" in manifest.incomplete_reasons
    assert manifest.reproducibility == "incomplete"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.2/x",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x",
        "http://[fc00::1]/x",
    ],
)
def test_safe_fetch_blocks_non_global_ipv4_and_ipv6(url):
    with pytest.raises(SafeFetchError, match="non-global"):
        SafeOutboundFetcher().validate(url)


def test_safe_fetch_fails_closed_on_mixed_dns_and_accepts_global_aaaa():
    mixed = SafeOutboundFetcher(resolver=lambda host, port: ["93.184.216.34", "127.0.0.1"])
    with pytest.raises(SafeFetchError, match="non-global"):
        mixed.validate("https://example.test/feed")

    ipv6 = SafeOutboundFetcher(
        resolver=lambda host, port: ["2606:2800:220:1:248:1893:25c8:1946"]
    ).validate("https://example.test/feed")
    assert ipv6.addresses == ("2606:2800:220:1:248:1893:25c8:1946",)


class _StubFetcher(SafeOutboundFetcher):
    def __init__(self, responses):
        super().__init__(resolver=lambda host, port: ["93.184.216.34"])
        self.responses = responses
        self.calls = []

    def _request_once(self, target, address, *, allowed_content_types=DEFAULT_CONTENT_TYPES):
        self.calls.append((target.url, address))
        return self.responses[target.url]


def test_safe_fetch_revalidates_redirect_destination():
    fetcher = _StubFetcher(
        {
            "https://public.test/start": SafeFetchResponse(
                "https://public.test/start",
                302,
                {"location": "http://127.0.0.1/admin"},
                b"",
            )
        }
    )
    with pytest.raises(SafeFetchError, match="non-global"):
        fetcher.fetch("https://public.test/start")
    assert len(fetcher.calls) == 1


def test_safe_fetch_blocks_decompression_bomb():
    raw = gzip.compress(b"x" * 10_000)
    fetcher = SafeOutboundFetcher(max_compressed_bytes=len(raw) + 1, max_bytes=100)
    with pytest.raises(SafeFetchError, match="decompressed"):
        fetcher._decode_body(raw, "gzip")


def test_safe_fetch_blocks_content_type_and_declared_or_streamed_oversize():
    fetcher = SafeOutboundFetcher(max_compressed_bytes=20, max_bytes=10)
    with pytest.raises(SafeFetchError, match="content-type"):
        fetcher._validate_response_headers(
            {"content-type": "application/octet-stream"}, DEFAULT_CONTENT_TYPES
        )
    with pytest.raises(SafeFetchError, match="compressed"):
        fetcher._validate_response_headers(
            {"content-type": "text/plain", "content-length": "21"},
            DEFAULT_CONTENT_TYPES,
        )
    with pytest.raises(SafeFetchError, match="decompressed"):
        fetcher._decode_body(b"x" * 11, "identity")


def test_pinned_backend_connects_to_vetted_ip(monkeypatch):
    backend = _PinnedBackend("public.test", "93.184.216.34")
    captured = {}

    def connect(host, port, **kwargs):
        captured["host"] = host
        return object()

    monkeypatch.setattr(backend._backend, "connect_tcp", connect)
    backend.connect_tcp("public.test", 443)
    assert captured["host"] == "93.184.216.34"


@needs_pg
def test_async_idempotency_manifest_rerun_and_snapshot_export(client):
    import psycopg

    suffix = uuid4().hex[:10]
    key = f"phase9-idempotency-{suffix}"
    body = {
        "engine": "fabric",
        "subject": f"ทดสอบ manifest และ idempotency {suffix}",
        "agents": 20,
        "population_acknowledged": True,
    }
    first = client.post("/runs/async", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 202
    run_id = first.json()["run_id"]
    assert first.json()["status"] == "complete"
    assert first.json()["status_url"] == f"/runs/{run_id}.json"

    reused = client.post("/runs/async", json=body, headers={"Idempotency-Key": key})
    assert reused.status_code == 202
    assert reused.json()["run_id"] == run_id
    assert reused.json()["reused"] is True
    conflict = client.post(
        "/runs/async",
        json={**body, "subject": body["subject"] + " เปลี่ยน"},
        headers={"Idempotency-Key": key},
    )
    assert conflict.status_code == 409

    manifest = client.get(f"/runs/{run_id}/manifest").json()
    assert manifest["schema_version"] == 1
    assert manifest["complete"] is True
    assert verify_manifest_hash(manifest)
    snapshot = client.get(f"/runs/{run_id}/snapshot").json()
    assert snapshot["manifest_hash"] == manifest["manifest_hash"]

    frozen = client.post(
        f"/runs/{run_id}/rerun",
        json={"input_mode": "frozen"},
        headers={"Idempotency-Key": f"phase9-frozen-{suffix}"},
    )
    assert frozen.status_code == 202
    frozen_id = frozen.json()["run_id"]
    frozen_manifest = client.get(f"/runs/{frozen_id}/manifest").json()
    assert frozen_manifest["spec"]["input_mode"] == "frozen"
    assert frozen_manifest["spec"]["source_run_id"] == run_id
    assert (
        frozen_manifest["spec"]["population_snapshot"]["segments_hash"]
        == manifest["spec"]["population_snapshot"]["segments_hash"]
    )

    latest = client.post(
        f"/runs/{run_id}/rerun",
        json={"input_mode": "latest"},
        headers={"Idempotency-Key": f"phase9-latest-{suffix}"},
    )
    assert latest.status_code == 202
    latest_id = latest.json()["run_id"]
    latest_manifest = client.get(f"/runs/{latest_id}/manifest").json()
    assert latest_manifest["spec"]["input_mode"] == "latest"

    with psycopg.connect(DSN) as conn:
        conn.execute(
            "UPDATE sim_runs SET payload = %s::jsonb WHERE run_id = %s",
            (json.dumps({"tampered_after_manifest": True}), run_id),
        )
    exported = client.get(f"/runs/{run_id}/export.json")
    assert exported.status_code == 200
    exported_body = exported.json()
    assert exported_body["watermark"]["manifest_hash"] == manifest["manifest_hash"]
    assert "tampered_after_manifest" not in exported_body["snapshot"]["result"]
    pdf = client.get(f"/runs/{run_id}/export.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    for target in (latest_id, frozen_id, run_id):
        client.delete(f"/runs/{target}")


@needs_pg
def test_legacy_run_is_labeled_without_reconstructed_provenance(client):
    import psycopg

    run_id = f"fabric-legacy-{uuid4().hex}"
    store = RunStore(DSN)
    store.create(
        run_id=run_id,
        engine="fabric",
        subject="ทดสอบ legacy incomplete",
        domain="ทดสอบ",
        agents=1,
        rounds=1,
        seed=1,
        config={},
        status="running",
    )
    store.finish(run_id, {"brief": {"headline_range": [0, 0], "fragility_index": 0}})
    legacy = {
        "run_id": run_id,
        "schema_version": 0,
        "complete": False,
        "reproducibility": "legacy-incomplete",
        "reason": "test legacy; provenance not reconstructed",
    }
    with psycopg.connect(DSN) as conn:
        conn.execute(
            "INSERT INTO run_manifests "
            "(run_id, schema_version, complete, config_hash, manifest_hash, "
            "reproducibility, spec, manifest) "
            "VALUES (%s, 0, false, '', '', 'legacy-incomplete', '{}'::jsonb, %s::jsonb)",
            (run_id, json.dumps(legacy, ensure_ascii=False)),
        )
    detail = client.get(f"/runs/{run_id}.json").json()
    assert detail["manifest"]["reproducibility"] == "legacy-incomplete"
    reproduction = next(
        check for check in detail["trust_scorecard"]["checks"] if check["id"] == "reproducibility"
    )
    assert reproduction["status"] != "pass"
    client.delete(f"/runs/{run_id}")


@needs_pg
def test_terminal_cas_cancel_finish_fail_race_and_stale_worker():
    import psycopg

    store = RunStore(DSN)
    race_id = f"fabric-race-{uuid4().hex}"
    store.create(
        run_id=race_id,
        engine="fabric",
        subject="ทดสอบ terminal race",
        domain="ทดสอบ",
        agents=1,
        rounds=1,
        seed=1,
        config={},
        status="running",
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        cancel_future = executor.submit(store.cancel, race_id, "race cancel")
        finish_future = executor.submit(store.finish, race_id, {"ok": True})
    assert sum([cancel_future.result(), finish_future.result()]) == 1
    terminal = store.state(race_id)
    assert terminal in {"complete", "canceled"}
    assert store.fail(race_id, "late failure") is False
    assert store.cancel(race_id, "late cancel") is False
    assert store.finish(race_id, {"late": True}) is False
    if terminal == "canceled":
        with pytest.raises(RunCanceledError):
            store.add_posts(race_id, [{"round_no": 1}])

    stale_id = f"fabric-stale-{uuid4().hex}"
    store.create(
        run_id=stale_id,
        engine="fabric",
        subject="ทดสอบ stale worker",
        domain="ทดสอบ",
        agents=1,
        rounds=1,
        seed=1,
        config={},
        status="running",
    )
    with psycopg.connect(DSN) as conn:
        conn.execute(
            "UPDATE sim_runs SET heartbeat_at = TIMESTAMPTZ '1900-01-01' WHERE run_id = %s",
            (stale_id,),
        )
    marked = store.mark_stale(
        running_after_s=100 * 365 * 24 * 60 * 60,
        queued_after_s=100 * 365 * 24 * 60 * 60,
    )
    assert stale_id in marked
    assert store.state(stale_id) == "error"
    assert store.finish(stale_id, {"late": True}) is False
    store.delete(stale_id)
    store.delete(race_id)
