"""Governance store — audit log (GOV-04) + prediction registry (TRUST-01 ขั้นต่ำ)

append-only บังคับที่ระดับ PostgreSQL trigger: UPDATE/DELETE ถูก RAISE EXCEPTION จาก DB เอง
— ไม่มี code path ฝั่ง Python สำหรับแก้/ลบ และต่อให้เขียน SQL ตรงก็ทำไม่ได้ (กฎเหล็กข้อ 3)

ทุก simulation run ต้องเขียน prediction record ≥ 1 รายการ — enforce ผ่าน finalize_run()
"""

from dataclasses import dataclass
from datetime import date

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
CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % on % is forbidden (GOV-04/TRUST-01)', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;
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
    confidence: float  # 0-1
    measurement: str  # วิธีวัดผลเมื่อครบกำหนด
    due_date: date
    model_version: str


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
                "(run_id, claim, direction, confidence, measurement, due_date, model_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    p.claim,
                    p.direction,
                    p.confidence,
                    p.measurement,
                    p.due_date,
                    p.model_version,
                ),
            )

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
