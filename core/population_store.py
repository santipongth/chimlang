"""Immutable PopulationSetV1 snapshots used by production runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.db import connection, require_schema
from core.run_manifest import canonical_hash
from simulation.persona import PersonaFactory
from simulation.persona_packs import validate_pack

_SCHEMA = """
CREATE TABLE IF NOT EXISTS population_sets (
    set_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_version INT NOT NULL CHECK (schema_version = 1),
    name TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('sample-default','persona-pack','project')),
    source_ref TEXT NOT NULL DEFAULT '',
    synthetic BOOLEAN NOT NULL,
    acknowledged BOOLEAN NOT NULL,
    content_hash TEXT NOT NULL,
    manifest JSONB NOT NULL,
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS population_sets_hash ON population_sets(content_hash);
CREATE INDEX IF NOT EXISTS population_sets_project ON population_sets(project_id, created_at DESC);
DROP TRIGGER IF EXISTS population_sets_append_only ON population_sets;
CREATE TRIGGER population_sets_append_only
    BEFORE UPDATE OR DELETE ON population_sets
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""


class PopulationSetStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
        require_schema(dsn)

    @staticmethod
    def _manifest(
        segments: list[dict[str, Any]],
        *,
        project_id: str,
        source_kind: str,
        source_ref: str,
        synthetic: bool,
        acknowledged: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "project_id": project_id,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "synthetic": synthetic,
            "acknowledged": acknowledged,
            "segments": segments,
            "segments_hash": canonical_hash(segments),
            "limitations": ["synthetic population assumptions; not a field poll or census estimate"]
            if synthetic
            else [],
        }

    def freeze(
        self,
        segments: list[dict[str, Any]],
        *,
        name: str,
        actor: str,
        source_kind: str,
        source_ref: str = "",
        project_id: str = "",
        synthetic: bool = True,
        acknowledged: bool = False,
    ) -> dict[str, Any]:
        if source_kind not in {"sample-default", "persona-pack", "project"}:
            raise ValueError("population source_kind ไม่ถูกต้อง")
        if synthetic and not acknowledged:
            raise ValueError("ต้องยอมรับก่อนว่า population เป็นข้อมูลสังเคราะห์ ไม่ใช่ผลสำรวจจริง")
        # Reuse the same validation contract as editable persona packs before freezing.
        validate_pack(name.strip() or "Frozen population", segments)
        PersonaFactory(segments=segments)
        manifest = self._manifest(
            segments,
            project_id=project_id.strip(),
            source_kind=source_kind,
            source_ref=source_ref.strip(),
            synthetic=synthetic,
            acknowledged=acknowledged,
        )
        content_hash = canonical_hash(manifest)
        with connection(self._dsn) as conn:
            existing = conn.execute(
                "SELECT set_id FROM population_sets WHERE content_hash = %s "
                "AND created_by = %s ORDER BY created_at DESC LIMIT 1",
                (content_hash, actor[:160]),
            ).fetchone()
            if existing:
                return self.get(existing[0])
            set_id = f"population-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
            conn.execute(
                "INSERT INTO population_sets "
                "(set_id, project_id, schema_version, name, source_kind, source_ref, synthetic, "
                "acknowledged, content_hash, manifest, created_by) "
                "VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)",
                (
                    set_id,
                    project_id.strip(),
                    (name.strip() or "Frozen population")[:200],
                    source_kind,
                    source_ref.strip()[:500],
                    synthetic,
                    acknowledged,
                    content_hash,
                    json.dumps(manifest, ensure_ascii=False),
                    actor[:160],
                ),
            )
        return self.get(set_id)

    def get(self, set_id: str) -> dict[str, Any]:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT set_id, project_id, created_at, schema_version, name, source_kind, "
                "source_ref, synthetic, acknowledged, content_hash, manifest, created_by "
                "FROM population_sets WHERE set_id = %s",
                (set_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"ไม่พบ PopulationSetV1 {set_id}")
        manifest = dict(row[10])
        return {
            "set_id": row[0],
            "project_id": row[1],
            "created_at": row[2].isoformat(),
            "schema_version": row[3],
            "name": row[4],
            "source_kind": row[5],
            "source_ref": row[6],
            "synthetic": row[7],
            "acknowledged": row[8],
            "content_hash": row[9],
            "manifest": manifest,
            "created_by": row[11],
            "hash_valid": canonical_hash(manifest) == row[9],
            "segments": list(manifest.get("segments") or []),
        }
