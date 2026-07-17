"""Phase 9 M2/M3: project/evidence/validation/rehearsal trust contracts."""

import math
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from api.app import _materialize_evidence_set, app
from api.models import RunBody
from api.routers.projects import _extract_upload
from api.routers.rehearsals import _loads, _preflight
from core.db import connection
from core.llm.budget import release_budget_reservation
from core.project_store import EvidenceStore, ProjectStore
from core.rehearsal_store import RehearsalStore
from core.validation_store import ValidationStore
from governance.pii import PIIRedactionError
from scripts.run_miracl_th import _load_queries, _metrics
from scripts.run_model_robustness import _metrics as _robustness_metrics

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม")


@needs_pg
def test_project_workflow_is_revisioned_and_cannot_skip_stages():
    store = ProjectStore(DSN)
    project = store.create(
        name=f"pytest project {uuid4()}",
        brief="ศึกษาผลกระทบมาตรการค่าโดยสาร",
        actor="pytest",
    )
    updated = store.update(project["project_id"], actor="pytest", stage="evidence")
    assert updated["stage"] == "evidence"
    assert updated["workflow"][0]["status"] == "complete"
    with pytest.raises(ValueError, match="ข้าม workflow"):
        store.update(project["project_id"], actor="pytest", stage="run")


@needs_pg
def test_evidence_versions_deduplicate_freeze_and_materialize_without_mutation():
    projects = ProjectStore(DSN)
    evidence = EvidenceStore(DSN)
    project = projects.create(
        name=f"pytest evidence {uuid4()}",
        brief="ทดสอบคลังหลักฐาน",
        actor="pytest",
    )
    first = evidence.add_content(
        project["project_id"],
        label="รายงานฉบับหนึ่ง",
        kind="text",
        content="ราคาค่าโดยสารลดลงร้อยละสิบในช่วงทดลอง",
        actor="pytest",
    )
    second = evidence.add_content(
        project["project_id"],
        label="สำเนารายงาน",
        kind="text",
        content="ราคาค่าโดยสารลดลงร้อยละสิบในช่วงทดลอง",
        actor="pytest",
    )
    assert first["status"] == "ready"
    assert second["status"] == "duplicate"
    assert second["duplicate_of"] == first["version_id"]

    frozen = evidence.freeze(
        project["project_id"],
        name="ชุดหลักฐานทดสอบ",
        actor="pytest",
    )
    assert frozen["schema_version"] == 1 and frozen["hash_valid"]
    sources, provenance = evidence.sources_for_set(frozen["set_id"])
    assert len(sources) == 1
    assert provenance["content_hash"] == frozen["content_hash"]

    frozen["versions"][0]["label"] = "แก้ใน memory"
    assert evidence.get_set(frozen["set_id"])["hash_valid"]


@needs_pg
def test_direct_evidence_pii_is_never_persisted_and_preview_has_counts_only():
    projects = ProjectStore(DSN)
    evidence = EvidenceStore(DSN)
    project = projects.create(
        name=f"pytest pii {uuid4()}",
        brief="ทดสอบ PII gate",
        actor="pytest",
    )
    raw = "ติดต่อ test.person@example.com เพื่อขอข้อมูล"
    preview = evidence.preview(raw)
    assert preview == {
        "safe_to_store": False,
        "pii_counts": {"email": 1},
        "policy": "direct-input-block; external-url-redact-and-verify",
    }
    with pytest.raises(PIIRedactionError):
        evidence.add_content(
            project["project_id"],
            label="ข้อมูลต้องห้าม",
            kind="text",
            content=raw,
            actor="pytest",
        )
    assert evidence.list_project(project["project_id"]) == []


@needs_pg
def test_run_materializes_frozen_evidence_set_with_hash_provenance():
    project = ProjectStore(DSN).create(
        name=f"pytest run evidence {uuid4()}",
        brief="ทดสอบ run lineage",
        actor="pytest",
    )
    evidence = EvidenceStore(DSN)
    evidence.add_content(
        project["project_id"],
        label="หลักฐาน",
        kind="text",
        content="ประชาชนใช้ระบบขนส่งสาธารณะเพิ่มขึ้น",
        actor="pytest",
    )
    frozen = evidence.freeze(project["project_id"], name="freeze", actor="pytest")
    body, provenance = _materialize_evidence_set(
        RunBody(
            engine="debate",
            subject="ประเมินมาตรการขนส่ง",
            evidence_set_id=frozen["set_id"],
        )
    )
    assert body.project_id == project["project_id"]
    assert body.sources[0]["text"]
    assert provenance["content_hash"] == frozen["content_hash"]
    with pytest.raises(Exception, match="debate"):
        _materialize_evidence_set(
            RunBody(
                engine="fabric",
                subject="ประเมินมาตรการขนส่ง",
                evidence_set_id=frozen["set_id"],
            )
        )


@needs_pg
def test_human_panel_import_requires_consent_and_rejects_pii():
    store = ValidationStore(DSN)
    kwargs = {
        "name": "pytest panel consent fixture",
        "consent_basis": "แบบยินยอมงานวิจัยฉบับทดสอบ",
        "collected_at": datetime.now(UTC),
        "rows": [{"case_id": "case-1", "prompt": "เห็นด้วยกับมาตรการหรือไม่", "expected": True}],
        "metadata": {"population": "ผู้ใหญ่ไทยกลุ่มทดสอบ"},
        "actor": "pytest",
    }
    with pytest.raises(ValueError, match="consent"):
        store.import_human_panel(consent_confirmed=False, **kwargs)
    imported = store.import_human_panel(consent_confirmed=True, **kwargs)
    assert imported["kind"] == "human_panel"
    assert imported["case_count"] == 1
    assert imported["metadata"]["outcomes_supplied_by_importer"] is True
    with pytest.raises(ValueError, match="PII"):
        store.import_human_panel(
            consent_confirmed=True,
            **{
                **kwargs,
                "name": f"pytest pii panel {uuid4()}",
                "rows": [
                    {
                        "case_id": "case-pii",
                        "prompt": "ติดต่อ somebody@example.com",
                        "expected": False,
                    }
                ],
            },
        )


@needs_pg
def test_rehearsal_events_reconstruct_transcript_and_terminal_cas():
    store = RehearsalStore(DSN)
    with pytest.raises(ValueError, match="ไม่พบ rehearsal"):
        store.acquire_operation(f"missing-{uuid4()}", "next")
    session = store.create(
        title=f"pytest rehearsal {uuid4()}",
        scenario="ชี้แจงมาตรการค่าโดยสาร",
        seed=41,
        netizens=2,
        max_turns=3,
        reactions_per_turn=1,
        actor="pytest",
    )
    session_id = session["session_id"]
    lease = store.acquire_operation(session_id, "pytest-first")
    with pytest.raises(ValueError, match="operation"):
        store.acquire_operation(session_id, "pytest-concurrent")
    store.release_operation(session_id, lease)
    next_lease = store.acquire_operation(session_id, "pytest-after-release")
    store.release_operation(session_id, next_lease)
    store.append_event(
        session_id,
        event_type="question",
        turn_no=1,
        actor="pytest",
        payload={
            "journalist_id": "economic",
            "journalist": "นักข่าวสายเศรษฐกิจ",
            "question": "ใช้งบเท่าไร",
            "latency_s": 0.5,
        },
        require_status="active",
    )
    store.append_event(
        session_id,
        event_type="answer",
        turn_no=1,
        actor="pytest",
        payload={"answer": "ใช้งบตามกรอบที่อนุมัติ", "reactions": ["กลุ่มหนึ่ง: รับทราบ"]},
        require_status="active",
    )
    detail = store.get(session_id)
    assert detail["turns"][0]["answered"]
    paused = store.transition(session_id, expected="active", target="paused", actor="pytest")
    assert paused["status"] == "paused"
    with pytest.raises(ValueError):
        store.transition(session_id, expected="active", target="paused", actor="pytest")
    store.transition(session_id, expected="paused", target="active", actor="pytest")
    finished = store.finish(
        session_id,
        scorecard={"summary": "สรุป", "simulation_estimate": True},
        actor="pytest",
    )
    assert finished["status"] == "complete"
    with pytest.raises(ValueError):
        store.finish(session_id, scorecard={}, actor="pytest")


@needs_pg
def test_rehearsal_preflight_reserves_monthly_budget_and_binds_ledger(monkeypatch):
    reservation_id = f"pytest-rehearsal-budget-{uuid4()}"
    monkeypatch.setattr("api.routers.rehearsals.effective_monthly_cap", lambda: 0.0)
    try:
        adapter, _ = _preflight(_loads(crowd_calls=1), reservation_id=reservation_id, reserve=True)
        with connection(DSN) as conn:
            row = conn.execute(
                "SELECT usd_reserved FROM monthly_budget_reservations WHERE reservation_id=%s",
                (reservation_id,),
            ).fetchone()
        assert row is not None and float(row[0]) > 0
        assert adapter._run_id == reservation_id
        assert adapter._monthly_reservation_id == reservation_id
    finally:
        release_budget_reservation(DSN, reservation_id)


def test_upload_parser_and_openapi_named_contracts():
    text, kind = _extract_upload("หลักฐาน.csv", "text/csv", "หัวข้อ,ค่า\nหนึ่ง,1".encode())
    assert kind == "csv" and "หัวข้อ" in text
    with pytest.raises(ValueError, match="รองรับ"):
        _extract_upload("image.png", "image/png", b"not-an-image")
    docx = BytesIO()
    with ZipFile(docx, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"x" * 10_000_001)
    with pytest.raises(ValueError, match="10 MB"):
        _extract_upload("bomb.docx", "application/vnd.openxmlformats", docx.getvalue())

    schema = app.openapi()
    assert schema["paths"]["/projects"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("ProjectListResponse")
    assert schema["paths"]["/validation/resolution-inbox"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("ResolutionInboxResponse")
    assert schema["paths"]["/rehearsals/{session_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("RehearsalResponse")


def test_miracl_sampling_and_metrics_are_deterministic():
    queries, available = _load_queries("q1\tหนึ่ง\nq2\tสอง\nq3\tสาม", 1)
    assert queries == {"q1": "หนึ่ง"} and available == 3
    metrics, rows = _metrics(
        {"q1": ["d2", "d1"], "q2": ["d3"]},
        {"q1": {"d1": 1}, "q2": {"d3": 2}},
    )
    assert metrics == {
        "recall_at_100": 1.0,
        "mrr_at_10": 0.75,
        "ndcg_at_10": pytest.approx((1 / math.log2(3) + 1) / 2),
        "query_count": 2,
    }
    assert len(rows) == 2


def test_model_robustness_metrics_report_agreement_without_claiming_accuracy():
    models = ["model-a", "model-b", "model-c"]
    cases = [{"case_id": "case-1"}, {"case_id": "case-2"}]
    rows = []
    for model, first, second in (
        ("model-a", "support", "oppose"),
        ("model-b", "support", "neutral"),
        ("model-c", "oppose", "neutral"),
    ):
        for case_id, stance in (("case-1", first), ("case-2", second)):
            rows.append(
                {
                    "model": model,
                    "case_id": case_id,
                    "status": "ok",
                    "stance": stance,
                    "confidence": 0.7,
                    "thai_rationale": True,
                    "latency_s": 0.1,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cost_usd": 0.001,
                }
            )
    metrics = _robustness_metrics(rows, models, cases)
    assert metrics["parse_success_rate"] == 1.0
    assert metrics["thai_rationale_rate"] == 1.0
    assert metrics["pairwise_stance_agreement"] == pytest.approx(2 / 6)
    assert "accuracy" not in metrics


@needs_pg
def test_model_robustness_dataset_and_report_are_append_only_measured_artifacts():
    store = ValidationStore(DSN)
    dataset = store.register_case_dataset(
        kind="model_robustness",
        name="pytest robustness fixture",
        revision="test-v1",
        license_name="synthetic",
        rows=[
            {
                "case_id": "case-1",
                "prompt": "ทดสอบความสอดคล้องของท่าที",
                "expected": {"ground_truth": None},
                "observed": {"model-a": {"stance": "neutral"}},
                "slice": {"domain": "policy"},
            }
        ],
        metadata={"no_human_ground_truth": True},
        actor="pytest",
    )
    report = store.register_report(
        dataset["dataset_id"],
        kind="model_robustness",
        metrics={"pairwise_stance_agreement": 1.0},
        raw_result_hash="a" * 64,
        metadata={"benchmark_complete": True, "no_human_ground_truth": True},
        actor="pytest",
    )
    assert dataset["case_count"] == 1
    assert report["trust_status"] == "measured"
    usability = store.register_case_dataset(
        kind="usability",
        name="pytest incomplete usability fixture",
        revision="test-v1",
        license_name="consented-aggregate",
        rows=[
            {
                "case_id": "P01-task-1",
                "prompt": "สร้างโปรเจกต์จาก brief",
                "observed": {"status": "complete"},
                "slice": {"task": "project"},
            }
        ],
        metadata={"consent_confirmed_count": 1},
        actor="pytest",
    )
    incomplete = store.register_report(
        usability["dataset_id"],
        kind="usability",
        metrics={"task_completion_rate": 1.0},
        raw_result_hash="b" * 64,
        metadata={
            "benchmark_complete": True,
            "participant_count": 1,
            "consent_confirmed_count": 1,
            "tasks_recorded": 1,
        },
        actor="pytest",
    )
    assert incomplete["trust_status"] == "unverified"


@needs_pg
def test_project_api_smoke_uses_named_response():
    client = TestClient(app)
    missing = client.get(f"/projects/missing-{uuid4()}/evidence")
    assert missing.status_code == 404
    response = client.post(
        "/projects",
        json={"name": f"pytest API {uuid4()}", "brief": "ศึกษาผลกระทบมาตรการ"},
    )
    assert response.status_code == 201
    assert response.json()["stage"] == "brief"
