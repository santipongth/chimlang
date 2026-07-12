"""Governance store — audit log (GOV-04) + prediction registry (TRUST-01 ขั้นต่ำ)

append-only บังคับที่ระดับ PostgreSQL trigger: UPDATE/DELETE ถูก RAISE EXCEPTION จาก DB เอง
— ไม่มี code path ฝั่ง Python สำหรับแก้/ลบ และต่อให้เขียน SQL ตรงก็ทำไม่ได้ (กฎเหล็กข้อ 3)

ทุก simulation run ต้องเขียน prediction record ≥ 1 รายการ — enforce ผ่าน finalize_run()
"""

from dataclasses import dataclass
from datetime import date, datetime

import psycopg

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
            f"run {run_id} ไม่มี prediction record — ทุก simulation run ต้องเขียน ≥ 1 "
            "(TRUST-01 / กฎเหล็กข้อ 3)"
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
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

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
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO prediction_registry "
                "(run_id, claim, direction, confidence, measurement, due_date, "
                " model_version, domain) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    p.claim,
                    p.direction,
                    p.confidence,
                    p.measurement,
                    p.due_date,
                    p.model_version,
                    p.domain,
                ),
            )

    # --- Calibration Engine (TRUST-02) ---

    def due_unresolved(self, as_of: date) -> list[DuePrediction]:
        """prediction ที่ครบกำหนดแล้วแต่ยังไม่ resolve — คิวงานของ Calibration Engine"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT p.id, p.run_id, p.claim, p.confidence, p.domain, p.due_date "
                "FROM prediction_registry p "
                "LEFT JOIN prediction_resolution r ON r.prediction_id = p.id "
                "WHERE p.due_date <= %s AND r.id IS NULL ORDER BY p.due_date, p.id",
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
        self, prediction_id: int, *, outcome: bool | float, resolver: str, note: str = ""
    ) -> float:
        """บันทึกผลจริง + คำนวณ Brier score = (confidence − outcome_value)² — append-only

        outcome: bool (เดิม) หรือ float ∈ {0, 0.5, 1} — 0.5 = เกิดขึ้นบางส่วน (P5-M3)
        resolve ซ้ำ prediction เดิม = ผิดกติกา (UNIQUE ที่ DB) — แก้ผลไม่ได้เช่นเดียวกับ registry
        """
        value = 1.0 if outcome is True else 0.0 if outcome is False else float(outcome)
        if value not in (0.0, 0.5, 1.0):
            raise ValueError("outcome ต้องเป็น true/false หรือ 0/0.5/1 (partial = 0.5)")
        # คอลัมน์ bool เดิมคงไว้เพื่อแถวเก่า/เครื่องมือเก่า — partial ไม่มีค่า bool ที่ซื่อสัตย์ จึงเป็น NULL
        flag = True if value == 1.0 else False if value == 0.0 else None
        with self._conn() as conn:
            conf = conn.execute(
                "SELECT confidence FROM prediction_registry WHERE id = %s", (prediction_id,)
            ).fetchone()
            if conf is None:
                raise ValueError(f"ไม่พบ prediction id {prediction_id}")
            brier = (conf[0] - value) ** 2
            conn.execute(
                "INSERT INTO prediction_resolution "
                "(prediction_id, outcome, outcome_value, brier, resolver, note) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (prediction_id, flag, value, brier, resolver, note),
            )
        return brier

    def calibration_summary(self) -> list[DomainCalibration]:
        """Brier score สะสมรายโดเมน เทียบ baseline (naive p=0.5 → 0.25)"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT p.domain, count(*), avg(r.brier) "
                "FROM prediction_resolution r "
                "JOIN prediction_registry p ON p.id = r.prediction_id "
                "GROUP BY p.domain ORDER BY p.domain"
            ).fetchall()
        return [
            DomainCalibration(domain=r[0], resolved=int(r[1]), mean_brier=float(r[2])) for r in rows
        ]

    def calibration_detail(self, as_of: date) -> dict:
        """ข้อมูลครบสำหรับหน้า Calibration (P5-M3) — อ่านอย่างเดียว

        คืน: overall Brier, per-domain (นับ ✓/~/✗), weekly trend, รายการ resolved,
        คิวครบกำหนด (due) และคำทำนายที่ยังไม่ถึงกำหนด (upcoming)
        """
        with self._conn() as conn:
            resolved_rows = conn.execute(
                "SELECT p.id, p.run_id, p.claim, p.domain, p.confidence, "
                "COALESCE(r.outcome_value, CASE WHEN r.outcome THEN 1.0 ELSE 0.0 END) AS value, "
                "r.brier, r.ts, r.note "
                "FROM prediction_resolution r JOIN prediction_registry p ON p.id = r.prediction_id "
                "ORDER BY r.ts DESC"
            ).fetchall()
            upcoming_rows = conn.execute(
                "SELECT p.id, p.claim, p.domain, p.confidence, p.due_date "
                "FROM prediction_registry p "
                "LEFT JOIN prediction_resolution r ON r.prediction_id = p.id "
                "WHERE p.due_date > %s AND r.id IS NULL ORDER BY p.due_date, p.id",
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

        due = [
            {
                "prediction_id": p.prediction_id,
                "claim": p.claim,
                "domain": p.domain,
                "confidence": p.confidence,
                "due_date": p.due_date.isoformat(),
            }
            for p in self.due_unresolved(as_of)
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

    def predictions_for_run(self, run_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT count(*) FROM prediction_registry WHERE run_id = %s", (run_id,)
            ).fetchone()
            return int(row[0])

    def finalize_run(self, run_id: str) -> None:
        """เรียกตอนจบทุก simulation run — ไม่มี prediction = run นี้ไม่ถูกต้อง (raise)"""
        if self.predictions_for_run(run_id) < 1:
            raise RunWithoutPredictionError(run_id)
