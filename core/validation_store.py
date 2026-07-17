"""Validation datasets, reports, and resolution ownership (P9-M2)."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from uuid import uuid4

from core.config import get_settings
from core.db import connection
from core.run_manifest import canonical_hash, canonical_json
from governance.pii import PIIDetector, load_allowlist
from governance.store import GovernanceStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS validation_datasets (
    dataset_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind TEXT NOT NULL CHECK (kind IN ('miracl_th','human_panel','model_robustness','usability')),
    name TEXT NOT NULL,
    revision TEXT NOT NULL,
    license TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS validation_cases (
    id BIGSERIAL PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES validation_datasets(dataset_id),
    case_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    expected JSONB NOT NULL,
    observed JSONB NOT NULL DEFAULT '{}',
    slice JSONB NOT NULL DEFAULT '{}',
    UNIQUE (dataset_id, case_id)
);
CREATE TABLE IF NOT EXISTS validation_reports (
    report_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES validation_datasets(dataset_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind TEXT NOT NULL,
    metrics JSONB NOT NULL,
    raw_result_hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS prediction_owner_events (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT NOT NULL REFERENCES prediction_registry(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    owner TEXT NOT NULL,
    actor TEXT NOT NULL
);
DROP TRIGGER IF EXISTS validation_datasets_append_only ON validation_datasets;
CREATE TRIGGER validation_datasets_append_only
    BEFORE UPDATE OR DELETE ON validation_datasets
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS validation_cases_append_only ON validation_cases;
CREATE TRIGGER validation_cases_append_only
    BEFORE UPDATE OR DELETE ON validation_cases
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS validation_reports_append_only ON validation_reports;
CREATE TRIGGER validation_reports_append_only
    BEFORE UPDATE OR DELETE ON validation_reports
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS prediction_owner_events_append_only ON prediction_owner_events;
CREATE TRIGGER prediction_owner_events_append_only
    BEFORE UPDATE OR DELETE ON prediction_owner_events
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""


def _wilson(successes: float, n: int) -> list[float] | None:
    if n < 1:
        return None
    p = successes / n
    z = 1.959963984540054
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


class ValidationStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    @staticmethod
    def _assert_pii_free(value) -> None:
        settings = get_settings()
        if not settings.pii_detector_enabled:
            raise RuntimeError("PII detector ถูกปิด — validation import ถูกปฏิเสธ")
        if PIIDetector(load_allowlist()).check(canonical_json(value)).blocked:
            raise ValueError("validation import มี PII — ไม่บันทึกข้อมูลดิบ")

    def import_human_panel(
        self,
        *,
        name: str,
        consent_confirmed: bool,
        consent_basis: str,
        collected_at: datetime,
        rows: list[dict],
        metadata: dict,
        actor: str,
    ) -> dict:
        if not consent_confirmed or len(consent_basis.strip()) < 8:
            raise ValueError("ต้องยืนยัน consent และระบุ consent basis ก่อน import")
        if not rows or len(rows) > 5000:
            raise ValueError("human panel import ต้องมี 1-5000 cases")
        normalized = []
        for index, row in enumerate(rows):
            case_id = str(row.get("case_id") or f"case-{index + 1}")[:160]
            prompt = str(row.get("prompt") or "").strip()[:20_000]
            expected = row.get("expected")
            if not prompt or expected is None:
                raise ValueError("ทุก case ต้องมี prompt และ observed human outcome ใน expected")
            normalized.append(
                {
                    "case_id": case_id,
                    "prompt": prompt,
                    "expected": expected,
                    "observed": row.get("observed") or {},
                    "slice": row.get("slice") or {},
                }
            )
        basis = {
            "kind": "human_panel",
            "name": name.strip(),
            "consent_basis": consent_basis.strip(),
            "collected_at": collected_at.astimezone(UTC).isoformat(),
            "rows": normalized,
            "metadata": metadata,
        }
        self._assert_pii_free(basis)
        dataset_id = f"validation-human-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        content_hash = canonical_hash(basis)
        stored_metadata = {
            **metadata,
            "consent_confirmed": True,
            "consent_basis": consent_basis.strip(),
            "collected_at": collected_at.astimezone(UTC).isoformat(),
            "case_count": len(normalized),
            "outcomes_supplied_by_importer": True,
        }
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO validation_datasets "
                "(dataset_id, kind, name, revision, license, content_hash, metadata, created_by) "
                "VALUES (%s,'human_panel',%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    dataset_id,
                    name.strip()[:200],
                    collected_at.astimezone(UTC).isoformat(),
                    "consent-restricted",
                    content_hash,
                    json.dumps(stored_metadata, ensure_ascii=False),
                    actor[:160],
                ),
            )
            conn.cursor().executemany(
                "INSERT INTO validation_cases "
                "(dataset_id, case_id, prompt, expected, observed, slice) "
                "VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)",
                [
                    (
                        dataset_id,
                        row["case_id"],
                        row["prompt"],
                        json.dumps(row["expected"], ensure_ascii=False),
                        json.dumps(row["observed"], ensure_ascii=False),
                        json.dumps(row["slice"], ensure_ascii=False),
                    )
                    for row in normalized
                ],
            )
        return self.get_dataset(dataset_id)

    def register_case_dataset(
        self,
        *,
        kind: str,
        name: str,
        revision: str,
        license_name: str,
        rows: list[dict],
        metadata: dict,
        actor: str,
    ) -> dict:
        if kind not in {"model_robustness", "usability"}:
            raise ValueError("case dataset รองรับ model_robustness หรือ usability เท่านั้น")
        if not rows or len(rows) > 5000:
            raise ValueError("case dataset ต้องมี 1-5000 cases")
        normalized = []
        for index, row in enumerate(rows):
            prompt = str(row.get("prompt") or "").strip()[:20_000]
            if not prompt:
                raise ValueError("ทุก case ต้องมี prompt")
            normalized.append(
                {
                    "case_id": str(row.get("case_id") or f"case-{index + 1}")[:160],
                    "prompt": prompt,
                    "expected": row.get("expected"),
                    "observed": row.get("observed") or {},
                    "slice": row.get("slice") or {},
                }
            )
        basis = {
            "kind": kind,
            "name": name.strip(),
            "revision": revision.strip(),
            "license": license_name.strip(),
            "rows": normalized,
            "metadata": metadata,
        }
        self._assert_pii_free(basis)
        dataset_id = f"validation-{kind.replace('_', '-')}-{uuid4().hex[:12]}"
        content_hash = canonical_hash(basis)
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO validation_datasets "
                "(dataset_id, kind, name, revision, license, content_hash, metadata, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    dataset_id,
                    kind,
                    name.strip()[:200],
                    revision.strip()[:200],
                    license_name.strip()[:100],
                    content_hash,
                    json.dumps({**metadata, "case_count": len(normalized)}, ensure_ascii=False),
                    actor[:160],
                ),
            )
            conn.cursor().executemany(
                "INSERT INTO validation_cases "
                "(dataset_id, case_id, prompt, expected, observed, slice) "
                "VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)",
                [
                    (
                        dataset_id,
                        row["case_id"],
                        row["prompt"],
                        json.dumps(row["expected"], ensure_ascii=False),
                        json.dumps(row["observed"], ensure_ascii=False),
                        json.dumps(row["slice"], ensure_ascii=False),
                    )
                    for row in normalized
                ],
            )
        return self.get_dataset(dataset_id)

    def register_dataset(
        self,
        *,
        kind: str,
        name: str,
        revision: str,
        license_name: str,
        content_hash: str,
        metadata: dict,
        actor: str,
    ) -> str:
        if kind != "miracl_th":
            raise ValueError("register_dataset รองรับ miracl_th เท่านั้น")
        dataset_id = f"validation-miracl-{uuid4().hex[:12]}"
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO validation_datasets "
                "(dataset_id, kind, name, revision, license, content_hash, metadata, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    dataset_id,
                    kind,
                    name[:200],
                    revision[:200],
                    license_name[:100],
                    content_hash,
                    json.dumps(metadata, ensure_ascii=False),
                    actor[:160],
                ),
            )
        return dataset_id

    def register_report(
        self,
        dataset_id: str,
        *,
        kind: str,
        metrics: dict,
        raw_result_hash: str,
        metadata: dict,
        actor: str,
    ) -> dict:
        report_id = f"validation-report-{uuid4().hex[:16]}"
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO validation_reports "
                "(report_id, dataset_id, kind, metrics, raw_result_hash, metadata, created_by) "
                "VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s)",
                (
                    report_id,
                    dataset_id,
                    kind[:100],
                    json.dumps(metrics, ensure_ascii=False),
                    raw_result_hash,
                    json.dumps(metadata, ensure_ascii=False),
                    actor[:160],
                ),
            )
        return self.get_report(report_id)

    def get_dataset(self, dataset_id: str) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT dataset_id, created_at, kind, name, revision, license, content_hash, "
                "metadata, created_by FROM validation_datasets WHERE dataset_id = %s",
                (dataset_id,),
            ).fetchone()
            count = conn.execute(
                "SELECT count(*) FROM validation_cases WHERE dataset_id = %s", (dataset_id,)
            ).fetchone()[0]
        if row is None:
            raise ValueError(f"ไม่พบ validation dataset {dataset_id}")
        return {
            "dataset_id": row[0],
            "created_at": row[1].isoformat(),
            "kind": row[2],
            "name": row[3],
            "revision": row[4],
            "license": row[5],
            "content_hash": row[6],
            "metadata": row[7],
            "created_by": row[8],
            "case_count": int(count),
        }

    def list_datasets(self) -> list[dict]:
        with connection(self._dsn) as conn:
            ids = conn.execute(
                "SELECT dataset_id FROM validation_datasets WHERE created_by <> 'pytest' "
                "AND name NOT LIKE 'pytest %%' ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        return [self.get_dataset(row[0]) for row in ids]

    def get_report(self, report_id: str) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT report_id, dataset_id, created_at, kind, metrics, raw_result_hash, "
                "metadata, created_by FROM validation_reports WHERE report_id = %s",
                (report_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"ไม่พบ validation report {report_id}")
        metadata = row[6]
        complete_measurement = metadata.get("benchmark_complete") is True and (
            row[3] in {"miracl_retrieval", "model_robustness"}
            or (
                row[3] == "usability"
                and int(metadata.get("participant_count") or 0) >= 5
                and int(metadata.get("consent_confirmed_count") or 0) >= 5
                and int(metadata.get("tasks_recorded") or 0) >= 25
            )
        )
        trust_status = (
            "measured"
            if complete_measurement
            else "audit"
            if row[3] == "benchmark_invalidation"
            else "unverified"
        )
        return {
            "report_id": row[0],
            "dataset_id": row[1],
            "created_at": row[2].isoformat(),
            "kind": row[3],
            "metrics": row[4],
            "raw_result_hash": row[5],
            "metadata": row[6],
            "created_by": row[7],
            "trust_status": trust_status,
        }

    def list_reports(self) -> list[dict]:
        with connection(self._dsn) as conn:
            ids = conn.execute(
                "SELECT report_id FROM validation_reports WHERE created_by <> 'pytest' "
                "ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        reports = [self.get_report(row[0]) for row in ids]
        invalidated = {
            str(report["metadata"].get("invalidates_report_id"))
            for report in reports
            if report["kind"] == "benchmark_invalidation"
        }
        for report in reports:
            if report["report_id"] in invalidated:
                report["trust_status"] = "invalidated"
        return reports

    def invalidate_report(self, report_id: str, *, reason: str, actor: str) -> dict:
        target = self.get_report(report_id)
        reason = reason.strip()
        if len(reason) < 8:
            raise ValueError("invalidation reason ต้องอธิบายเหตุผล")
        metadata = {"invalidates_report_id": report_id, "reason": reason}
        return self.register_report(
            target["dataset_id"],
            kind="benchmark_invalidation",
            metrics={},
            raw_result_hash=canonical_hash(metadata),
            metadata=metadata,
            actor=actor,
        )

    def assign_owner(self, prediction_id: int, *, owner: str, actor: str) -> dict:
        owner = owner.strip()[:160]
        if not owner:
            raise ValueError("owner ห้ามว่าง")
        self._assert_pii_free({"owner": owner})
        with connection(self._dsn) as conn:
            if not conn.execute(
                "SELECT 1 FROM prediction_registry WHERE id = %s", (prediction_id,)
            ).fetchone():
                raise ValueError(f"ไม่พบ prediction {prediction_id}")
            row = conn.execute(
                "INSERT INTO prediction_owner_events (prediction_id, owner, actor) "
                "VALUES (%s,%s,%s) RETURNING created_at",
                (prediction_id, owner, actor[:160]),
            ).fetchone()
        return {
            "prediction_id": prediction_id,
            "owner": owner,
            "assigned_at": row[0].isoformat(),
            "actor": actor,
        }

    def resolution_inbox(self, as_of: date) -> dict:
        calibration = GovernanceStore(self._dsn).calibration_detail(
            as_of, include_test=False, include_legacy=False
        )
        with connection(self._dsn) as conn:
            owner_rows = conn.execute(
                "SELECT DISTINCT ON (prediction_id) prediction_id, owner, created_at "
                "FROM prediction_owner_events ORDER BY prediction_id, id DESC"
            ).fetchall()
        owners = {
            int(row[0]): {"owner": row[1], "assigned_at": row[2].isoformat()} for row in owner_rows
        }
        for section in ("due", "upcoming"):
            for item in calibration[section]:
                owner = owners.get(
                    int(item["prediction_id"]),
                    {"owner": "", "assigned_at": None},
                )
                item.update(owner)

        items = calibration["items"]
        briers = [float(item["brier"]) for item in items]
        mean = sum(briers) / len(briers) if briers else None
        if len(briers) > 1 and mean is not None:
            variance = sum((value - mean) ** 2 for value in briers) / (len(briers) - 1)
            margin = 1.959963984540054 * math.sqrt(variance / len(briers))
            brier_ci = [max(0.0, mean - margin), min(1.0, mean + margin)]
        elif mean is not None:
            brier_ci = [mean, mean]
        else:
            brier_ci = None

        ece = 0.0
        enriched_bins = []
        total = max(1, calibration["sample_size"])
        for item in calibration["reliability"]:
            observed = item["observed_rate"]
            confidence = item["mean_confidence"]
            if observed is not None and confidence is not None:
                ece += item["n"] / total * abs(observed - confidence)
            successes = float(observed or 0) * int(item["n"])
            enriched_bins.append({**item, "observed_ci95": _wilson(successes, int(item["n"]))})
        return {
            "as_of": as_of.isoformat(),
            "due": calibration["due"],
            "upcoming": calibration["upcoming"],
            "resolved": calibration["items"],
            "metrics": {
                "sample_size": calibration["sample_size"],
                "mean_brier": mean,
                "mean_brier_ci95": brier_ci,
                "ece": ece if calibration["sample_size"] else None,
                "reliability": enriched_bins,
            },
            "resolution_requires_evidence": True,
        }
