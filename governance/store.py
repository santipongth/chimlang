"""Governance store — audit log (GOV-04) + prediction registry (TRUST-01 ขั้นต่ำ)

append-only บังคับที่ระดับ PostgreSQL trigger: UPDATE/DELETE ถูก RAISE EXCEPTION จาก DB เอง
— ไม่มี code path ฝั่ง Python สำหรับแก้/ลบ และต่อให้เขียน SQL ตรงก็ทำไม่ได้ (กฎเหล็กข้อ 3)

ทุก simulation run ต้องเขียน prediction record ≥ 1 รายการ — enforce ผ่าน finalize_run()
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlparse

from core.db import connection, require_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    run_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS prediction_registry (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT NOT NULL,
    claim TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    measurement TEXT NOT NULL,
    due_date DATE NOT NULL,
    model_version TEXT NOT NULL
);
ALTER TABLE prediction_registry ADD COLUMN IF NOT EXISTS domain TEXT NOT NULL DEFAULT 'ทั่วไป';
CREATE TABLE IF NOT EXISTS prediction_resolution (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    prediction_id BIGINT NOT NULL UNIQUE REFERENCES prediction_registry(id),
    outcome BOOLEAN,
    brier DOUBLE PRECISION NOT NULL,
    resolver TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
-- P5-M3: outcome 3 ค่า (เกิดจริง=1 / บางส่วน=0.5 / ไม่เกิด=0) — คอลัมน์ใหม่ (บวกได้ ห้ามแก้แถวเดิม)
-- แถวเก่าไม่ backfill (append-only) — อ่านผ่าน COALESCE(outcome_value, outcome::int) เสมอ
ALTER TABLE prediction_resolution ADD COLUMN IF NOT EXISTS outcome_value DOUBLE PRECISION
    CHECK (outcome_value IN (0.0, 0.5, 1.0));
ALTER TABLE prediction_resolution ALTER COLUMN outcome DROP NOT NULL;
CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % on % is forbidden (GOV-04/TRUST-01)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS prediction_resolution_append_only ON prediction_resolution;
CREATE TRIGGER prediction_resolution_append_only
    BEFORE UPDATE OR DELETE ON prediction_resolution
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS prediction_registry_append_only ON prediction_registry;
CREATE TRIGGER prediction_registry_append_only
    BEFORE UPDATE OR DELETE ON prediction_registry
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""


class RunWithoutPredictionError(RuntimeError):
    def __init__(self, run_id: str):
        super().__init__(
            f"run {run_id} ไม่มี SimulationFinding หรือ Prediction — ผลรันไม่ผ่าน trust contract"
        )


@dataclass(frozen=True)
class Prediction:
    claim: str
    direction: str  # เช่น "ลดลง" / "เพิ่มขึ้น" / "เกิดขึ้น"
    confidence: float  # 0-1 — ความน่าจะเป็นที่ claim (ตามทิศที่ระบุ) จะเป็นจริง
    measurement: str  # วิธีวัดผลเมื่อครบกำหนด
    due_date: date
    model_version: str
    domain: str = "ทั่วไป"  # นโยบาย | ธุรกิจ/การตลาด | กระแสสังคม | ทั่วไป (TRUST-02 รายโดเมน)
    source_kind: str = "legacy"
    forecast_type: str = "binary"
    provenance: dict = field(default_factory=dict)
    created_by: str = ""


@dataclass(frozen=True)
class SimulationFinding:
    summary: str
    metrics: dict
    provenance: dict
    model_version: str


@dataclass(frozen=True)
class DuePrediction:
    prediction_id: int
    run_id: str
    claim: str
    confidence: float
    domain: str
    due_date: date


@dataclass(frozen=True)
class DomainCalibration:
    domain: str
    resolved: int
    mean_brier: float
    baseline_brier: float = 0.25  # naive forecast p=0.5 → Brier 0.25 เสมอ

    @property
    def better_than_baseline(self) -> bool:
        return self.mean_brier < self.baseline_brier


class GovernanceStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return connection(self._dsn)

    def setup(self) -> None:
        require_schema(self._dsn)

    def append_audit(
        self, *, actor: str, action: str, run_id: str, config_hash: str, detail: str = ""
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (actor, action, run_id, config_hash, detail) "
                "VALUES (%s, %s, %s, %s, %s)",
                (actor, action, run_id, config_hash, detail),
            )

    def register_prediction(self, run_id: str, p: Prediction) -> None:
        if p.forecast_type != "binary":
            raise ValueError("ระยะแรกรองรับ forecast_type=binary เท่านั้น")
        if p.source_kind == "legacy":
            # Compatibility for old call sites. New API predictions set an explicit source.
            pass
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO prediction_registry "
                "(run_id, claim, direction, confidence, measurement, due_date, "
                "model_version, domain, source_kind, forecast_type, provenance, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    p.claim,
                    p.direction,
                    p.confidence,
                    p.measurement,
                    p.due_date,
                    p.model_version,
                    p.domain,
                    p.source_kind,
                    p.forecast_type,
                    json.dumps(p.provenance, ensure_ascii=False),
                    p.created_by,
                ),
            )

    def register_finding(self, run_id: str, finding: SimulationFinding) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "INSERT INTO simulation_findings "
                "(run_id, summary, metrics, provenance, model_version) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    run_id,
                    finding.summary,
                    json.dumps(finding.metrics, ensure_ascii=False),
                    json.dumps(finding.provenance, ensure_ascii=False),
                    finding.model_version,
                ),
            ).fetchone()
        return int(row[0])

    # --- Calibration Engine (TRUST-02) ---

    def due_unresolved(
        self,
        as_of: date,
        *,
        include_test: bool = True,
        include_legacy: bool = False,
    ) -> list[DuePrediction]:
        """prediction ที่ครบกำหนดแล้วแต่ยังไม่ resolve — คิวงานของ Calibration Engine

        include_test=False: กรอง domain 'ทดสอบ%' ออก (ขยะจาก test suite ใน dev DB —
        registry เป็น append-only ลบไม่ได้ จึงกรองที่ชั้นอ่านแทน; UI ใช้โหมดนี้)
        """
        cond = "" if include_test else " AND p.domain NOT LIKE 'ทดสอบ%%'"
        if not include_legacy:
            cond += " AND p.source_kind <> 'legacy'"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT p.id, p.run_id, p.claim, p.confidence, p.domain, p.due_date "
                "FROM prediction_registry p "
                "LEFT JOIN prediction_resolution r ON r.prediction_id = p.id "
                f"WHERE p.due_date <= %s AND r.id IS NULL{cond} ORDER BY p.due_date, p.id",
                (as_of,),
            ).fetchall()
        return [
            DuePrediction(
                prediction_id=r[0],
                run_id=r[1],
                claim=r[2],
                confidence=r[3],
                domain=r[4],
                due_date=r[5],
            )
            for r in rows
        ]

    def resolve_prediction(
        self,
        prediction_id: int,
        *,
        outcome: bool,
        resolver: str,
        observed_at: datetime,
        evidence_url: str,
        evidence_name: str,
        note: str = "",
    ) -> float:
        """Append a binary observation with evidence; legacy partial rows stay readable."""
        if not isinstance(outcome, bool):
            raise ValueError("prediction ใหม่ resolve ได้เฉพาะ outcome แบบ binary true/false")
        parsed = urlparse(evidence_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("evidence_url ต้องเป็น URL แบบ http(s)")
        if not evidence_name.strip():
            raise ValueError("ต้องระบุชื่อหลักฐาน")
        value = 1.0 if outcome else 0.0
        with self._conn() as conn:
            conf = conn.execute(
                "SELECT confidence, source_kind FROM prediction_registry WHERE id = %s",
                (prediction_id,),
            ).fetchone()
            if conf is None:
                raise ValueError(f"ไม่พบ prediction id {prediction_id}")
            if conf[1] == "legacy":
                raise ValueError("legacy prediction อ่านได้แต่สร้าง resolution ใหม่ไม่ได้")
            brier = (conf[0] - value) ** 2
            conn.execute(
                "INSERT INTO prediction_resolution "
                "(prediction_id, outcome, outcome_value, brier, resolver, observed_at, "
                "evidence_url, evidence_name, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    prediction_id,
                    outcome,
                    value,
                    brier,
                    resolver,
                    observed_at,
                    evidence_url.strip(),
                    evidence_name.strip()[:200],
                    note,
                ),
            )
        return brier

    def calibration_summary(self) -> list[DomainCalibration]:
        """Brier score สะสมรายโดเมน เทียบ baseline (naive p=0.5 → 0.25)"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT p.domain, count(*), avg(r.brier) "
                "FROM prediction_resolution r "
                "JOIN prediction_registry p ON p.id = r.prediction_id "
                "WHERE p.source_kind <> 'legacy' "
                "GROUP BY p.domain ORDER BY p.domain"
            ).fetchall()
        return [
            DomainCalibration(domain=r[0], resolved=int(r[1]), mean_brier=float(r[2])) for r in rows
        ]

    def calibration_detail(
        self,
        as_of: date,
        *,
        include_test: bool = True,
        include_legacy: bool = False,
    ) -> dict:
        """ข้อมูลครบสำหรับหน้า Calibration (P5-M3) — อ่านอย่างเดียว

        คืน: overall Brier, per-domain (นับ ✓/~/✗), weekly trend, รายการ resolved,
        คิวครบกำหนด (due) และคำทำนายที่ยังไม่ถึงกำหนด (upcoming)
        include_test=False: กรอง domain 'ทดสอบ%' ออกทุกส่วน (UI ใช้โหมดนี้ — ดู due_unresolved)
        """
        cond = "" if include_test else " AND p.domain NOT LIKE 'ทดสอบ%%'"
        if not include_legacy:
            cond += " AND p.source_kind <> 'legacy'"
        with self._conn() as conn:
            resolved_rows = conn.execute(
                "SELECT p.id, p.run_id, p.claim, p.domain, p.confidence, "
                "COALESCE(r.outcome_value, CASE WHEN r.outcome THEN 1.0 ELSE 0.0 END) AS value, "
                "r.brier, r.ts, r.note, p.source_kind, r.observed_at, r.evidence_url, "
                "r.evidence_name "
                "FROM prediction_resolution r JOIN prediction_registry p ON p.id = r.prediction_id "
                f"WHERE true{cond} ORDER BY r.ts DESC"
            ).fetchall()
            upcoming_rows = conn.execute(
                "SELECT p.id, p.claim, p.domain, p.confidence, p.due_date "
                "FROM prediction_registry p "
                "LEFT JOIN prediction_resolution r ON r.prediction_id = p.id "
                f"WHERE p.due_date > %s AND r.id IS NULL{cond} ORDER BY p.due_date, p.id",
                (as_of,),
            ).fetchall()

        items = [
            {
                "prediction_id": r[0],
                "run_id": r[1],
                "claim": r[2],
                "domain": r[3],
                "confidence": float(r[4]),
                "outcome_value": float(r[5]),
                "brier": float(r[6]),
                "resolved_at": r[7].isoformat(),
                "note": r[8],
                "source_kind": r[9],
                "observed_at": r[10].isoformat() if r[10] else None,
                "evidence_url": r[11],
                "evidence_name": r[12],
            }
            for r in resolved_rows
        ]
        overall = sum(i["brier"] for i in items) / len(items) if items else None

        domains: dict[str, dict] = {}
        for i in items:
            d = domains.setdefault(
                i["domain"], {"n": 0, "brier_sum": 0.0, "happened": 0, "partial": 0, "didnt": 0}
            )
            d["n"] += 1
            d["brier_sum"] += i["brier"]
            key = (
                "happened"
                if i["outcome_value"] == 1.0
                else "partial"
                if i["outcome_value"] == 0.5
                else "didnt"
            )
            d[key] += 1
        domain_list = [
            {
                "domain": name,
                "n": d["n"],
                "brier": d["brier_sum"] / d["n"],
                "happened": d["happened"],
                "partial": d["partial"],
                "didnt": d["didnt"],
            }
            for name, d in sorted(domains.items())
        ]

        # trend รายสัปดาห์ (epoch-week ของเวลาที่ resolve) เก่า → ใหม่
        week_ms = 7 * 86400
        trend_map: dict[int, list[float]] = {}
        for i in items:
            ts = datetime.fromisoformat(i["resolved_at"]).timestamp()
            bucket = int(ts // week_ms) * week_ms
            trend_map.setdefault(bucket, []).append(i["brier"])
        trend = [
            {"t": bucket, "brier": sum(v) / len(v), "n": len(v)}
            for bucket, v in sorted(trend_map.items())
        ]

        reliability = []
        histogram = []
        for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
            upper = lower + 0.2
            bucket = [
                i
                for i in items
                if (
                    lower <= i["confidence"] <= upper
                    if upper == 1.0
                    else lower <= i["confidence"] < upper
                )
            ]
            n = len(bucket)
            reliability.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "n": n,
                    "mean_confidence": (sum(i["confidence"] for i in bucket) / n if n else None),
                    "observed_rate": (sum(i["outcome_value"] for i in bucket) / n if n else None),
                    "standard_error": ((0.25 / n) ** 0.5 if n else None),
                }
            )
            histogram.append({"lower": lower, "upper": upper, "n": n})

        due = [
            {
                "prediction_id": p.prediction_id,
                "claim": p.claim,
                "domain": p.domain,
                "confidence": p.confidence,
                "due_date": p.due_date.isoformat(),
            }
            for p in self.due_unresolved(
                as_of, include_test=include_test, include_legacy=include_legacy
            )
        ]
        upcoming = [
            {
                "prediction_id": r[0],
                "claim": r[1],
                "domain": r[2],
                "confidence": float(r[3]),
                "due_date": r[4].isoformat(),
            }
            for r in upcoming_rows
        ]
        return {
            "overall_brier": overall,
            "resolved_total": len(items),
            "domains": domain_list,
            "trend": trend,
            "items": items,
            "due": due,
            "upcoming": upcoming,
            "baseline_brier": 0.25,
            "reliability": reliability,
            "confidence_histogram": histogram,
            "sample_size": len(items),
            "include_legacy": include_legacy,
        }

    def recent_runs(self, limit: int = 30) -> list[dict]:
        """สรุปรันล่าสุดจาก audit log (read-only) — สำหรับหน้าการจัดการรัน (P4-M1)"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT a.run_id, min(a.ts) AS started, "
                "bool_or(a.action = 'report_exported') AS exported, "
                "(SELECT count(*) FROM prediction_registry p WHERE p.run_id = a.run_id) AS preds "
                "FROM audit_log a GROUP BY a.run_id ORDER BY started DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": r[0],
                "started": r[1].isoformat(),
                "exported": bool(r[2]),
                "predictions": int(r[3]),
            }
            for r in rows
        ]

    def insights(self) -> dict:
        """Cross-run analytics (P5-M6) — อ่านอย่างเดียวจาก audit log + registry

        ทุกตัวเลขย้อนถึงข้อมูลดิบได้: runs จาก audit (GOV-04), predictions จาก registry
        """
        with self._conn() as conn:
            total_runs = conn.execute("SELECT count(DISTINCT run_id) FROM audit_log").fetchone()[0]
            exports = conn.execute(
                "SELECT count(*) FROM audit_log WHERE action = 'report_exported'"
            ).fetchone()[0]
            per_day = conn.execute(
                "SELECT to_char(date_trunc('day', started), 'YYYY-MM-DD') AS day, count(*) "
                "FROM (SELECT run_id, min(ts) AS started FROM audit_log GROUP BY run_id) t "
                "GROUP BY day ORDER BY day DESC LIMIT 30"
            ).fetchall()
            pred_by_domain = conn.execute(
                "SELECT p.domain, count(*), count(r.id) "
                "FROM prediction_registry p "
                "LEFT JOIN prediction_resolution r ON r.prediction_id = p.id "
                "GROUP BY p.domain ORDER BY count(*) DESC"
            ).fetchall()
        return {
            "total_runs": int(total_runs),
            "exports": int(exports),
            "runs_per_day": [{"day": r[0], "runs": int(r[1])} for r in reversed(per_day)],
            "predictions_by_domain": [
                {"domain": r[0], "total": int(r[1]), "resolved": int(r[2])} for r in pred_by_domain
            ],
        }

    def predictions_for_run(self, run_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT count(*) FROM prediction_registry WHERE run_id = %s", (run_id,)
            ).fetchone()
            return int(row[0])

    def results_for_run(self, run_id: str) -> dict:
        with self._conn() as conn:
            predictions = conn.execute(
                "SELECT p.id, p.ts, p.claim, p.direction, p.confidence, p.measurement, "
                "p.due_date, p.model_version, p.domain, p.source_kind, p.forecast_type, "
                "p.provenance, r.outcome_value, r.observed_at, r.evidence_url, r.evidence_name, "
                "r.note, r.brier FROM prediction_registry p LEFT JOIN prediction_resolution r "
                "ON r.prediction_id = p.id WHERE p.run_id = %s ORDER BY p.id",
                (run_id,),
            ).fetchall()
            findings = conn.execute(
                "SELECT id, ts, summary, metrics, provenance, model_version "
                "FROM simulation_findings WHERE run_id = %s ORDER BY id",
                (run_id,),
            ).fetchall()
        return {
            "predictions": [
                {
                    "prediction_id": r[0],
                    "created_at": r[1].isoformat(),
                    "claim": r[2],
                    "direction": r[3],
                    "probability": float(r[4]),
                    "measurement": r[5],
                    "due_date": r[6].isoformat(),
                    "model_version": r[7],
                    "domain": r[8],
                    "source_kind": r[9],
                    "forecast_type": r[10],
                    "provenance": r[11],
                    "resolution": (
                        {
                            "outcome": bool(r[12]),
                            "observed_at": r[13].isoformat() if r[13] else None,
                            "evidence_url": r[14],
                            "evidence_name": r[15],
                            "note": r[16],
                            "brier": float(r[17]),
                        }
                        if r[12] is not None
                        else None
                    ),
                }
                for r in predictions
            ],
            "findings": [
                {
                    "finding_id": r[0],
                    "created_at": r[1].isoformat(),
                    "summary": r[2],
                    "metrics": r[3],
                    "provenance": r[4],
                    "model_version": r[5],
                }
                for r in findings
            ],
        }

    def finalize_run(self, run_id: str) -> None:
        """Every run must yield a finding or a measurable real-world prediction."""
        with self._conn() as conn:
            finding_count = conn.execute(
                "SELECT count(*) FROM simulation_findings WHERE run_id = %s", (run_id,)
            ).fetchone()[0]
        if self.predictions_for_run(run_id) < 1 and int(finding_count) < 1:
            raise RunWithoutPredictionError(run_id)
