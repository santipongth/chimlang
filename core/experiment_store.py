"""Operational experiment workspaces for run comparison and sensitivity analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from core.db import connection, require_schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment_workspaces (
    experiment_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('sweep', 'comparison')),
    base_config JSONB NOT NULL DEFAULT '{}',
    dimensions JSONB NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS experiment_members (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiment_workspaces(experiment_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    variant JSONB NOT NULL DEFAULT '{}',
    UNIQUE (experiment_id, run_id)
);
CREATE INDEX IF NOT EXISTS experiment_members_run ON experiment_members (run_id);
"""


class ExperimentStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def setup(self) -> None:
        require_schema(self._dsn)

    def create(
        self,
        *,
        name: str,
        kind: str,
        base_config: dict,
        dimensions: dict,
        created_by: str,
    ) -> str:
        experiment_id = f"exp-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO experiment_workspaces "
                "(experiment_id, name, kind, base_config, dimensions, created_by) "
                "VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)",
                (
                    experiment_id,
                    name.strip()[:160] or "Untitled experiment",
                    kind,
                    json.dumps(base_config, ensure_ascii=False),
                    json.dumps(dimensions, ensure_ascii=False),
                    created_by[:160],
                ),
            )
        return experiment_id

    def add_member(self, experiment_id: str, run_id: str, variant: dict) -> None:
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO experiment_members (experiment_id, run_id, variant) "
                "VALUES (%s, %s, %s::jsonb) ON CONFLICT (experiment_id, run_id) DO NOTHING",
                (experiment_id, run_id, json.dumps(variant, ensure_ascii=False)),
            )

    def list(self, *, limit: int = 50) -> list[dict]:
        with connection(self._dsn) as conn:
            rows = conn.execute(
                "SELECT w.experiment_id, w.created_at, w.name, w.kind, w.dimensions, "
                "count(m.id) FROM experiment_workspaces w LEFT JOIN experiment_members m "
                "ON m.experiment_id = w.experiment_id GROUP BY w.experiment_id "
                "ORDER BY w.created_at DESC LIMIT %s",
                (max(1, min(200, limit)),),
            ).fetchall()
        return [
            {
                "experiment_id": row[0],
                "created_at": row[1].isoformat(),
                "name": row[2],
                "kind": row[3],
                "dimensions": row[4],
                "run_count": row[5],
            }
            for row in rows
        ]

    def get(self, experiment_id: str) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT experiment_id, created_at, name, kind, base_config, dimensions, created_by "
                "FROM experiment_workspaces WHERE experiment_id = %s",
                (experiment_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ experiment {experiment_id}")
            members = conn.execute(
                "SELECT run_id, variant FROM experiment_members WHERE experiment_id = %s "
                "ORDER BY id",
                (experiment_id,),
            ).fetchall()
        return {
            "experiment_id": row[0],
            "created_at": row[1].isoformat(),
            "name": row[2],
            "kind": row[3],
            "base_config": row[4],
            "dimensions": row[5],
            "created_by": row[6],
            "members": [{"run_id": member[0], "variant": member[1]} for member in members],
        }

    def delete(self, experiment_id: str) -> bool:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "DELETE FROM experiment_workspaces WHERE experiment_id = %s "
                "RETURNING experiment_id",
                (experiment_id,),
            ).fetchone()
        return row is not None
