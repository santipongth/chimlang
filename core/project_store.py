"""Project workflow and immutable EvidenceSetV1 storage (P9-M2)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from core.config import get_settings
from core.db import connection, require_schema
from core.run_manifest import canonical_hash
from core.safe_fetch import SafeOutboundFetcher
from governance.pii import PIIDetector, PIIRedactionError, load_allowlist
from simulation.sources import validate_external_url

PROJECT_STAGES = (
    "brief",
    "evidence",
    "population",
    "assumptions",
    "run",
    "compare",
    "decision",
    "resolution",
)
MAX_EVIDENCE_CHARS = 2_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    name TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (
        stage IN (
            'brief','evidence','population','assumptions',
            'run','compare','decision','resolution'
        )
    ),
    brief TEXT NOT NULL DEFAULT '',
    population JSONB NOT NULL DEFAULT '{}',
    assumptions JSONB NOT NULL DEFAULT '[]',
    decision TEXT NOT NULL DEFAULT '',
    resolution TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS project_revisions (
    revision_id BIGSERIAL PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT NOT NULL,
    snapshot JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS project_runs (
    id BIGSERIAL PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    run_id TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, run_id)
);
CREATE TABLE IF NOT EXISTS evidence_items (
    item_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    label TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('text','txt','csv','pdf','docx','url','rss')),
    source_url TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS evidence_versions (
    version_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES evidence_items(item_id) ON DELETE CASCADE,
    version_no INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    byte_size BIGINT NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'text/plain',
    status TEXT NOT NULL CHECK (status IN ('ready','redacted','duplicate')),
    source_health TEXT NOT NULL CHECK (source_health IN ('healthy','uploaded')),
    duplicate_of TEXT NOT NULL DEFAULT '',
    pii_redactions JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT '',
    UNIQUE (item_id, version_no)
);
CREATE INDEX IF NOT EXISTS evidence_versions_hash ON evidence_versions(content_hash);
CREATE TABLE IF NOT EXISTS evidence_sets (
    set_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_version INT NOT NULL CHECK (schema_version = 1),
    name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    manifest JSONB NOT NULL,
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS evidence_set_members (
    id BIGSERIAL PRIMARY KEY,
    set_id TEXT NOT NULL REFERENCES evidence_sets(set_id),
    version_id TEXT NOT NULL REFERENCES evidence_versions(version_id),
    ordinal INT NOT NULL,
    UNIQUE (set_id, version_id),
    UNIQUE (set_id, ordinal)
);
CREATE INDEX IF NOT EXISTS evidence_sets_project ON evidence_sets(project_id, created_at DESC);
DROP TRIGGER IF EXISTS project_revisions_append_only ON project_revisions;
CREATE TRIGGER project_revisions_append_only
    BEFORE UPDATE OR DELETE ON project_revisions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS evidence_versions_append_only ON evidence_versions;
CREATE TRIGGER evidence_versions_append_only
    BEFORE UPDATE OR DELETE ON evidence_versions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS evidence_sets_append_only ON evidence_sets;
CREATE TRIGGER evidence_sets_append_only
    BEFORE UPDATE OR DELETE ON evidence_sets
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
DROP TRIGGER IF EXISTS evidence_set_members_append_only ON evidence_set_members;
CREATE TRIGGER evidence_set_members_append_only
    BEFORE UPDATE OR DELETE ON evidence_set_members
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""


def _clean_html(value: str) -> str:
    value = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _clean_rss(value: str) -> str:
    entries = re.findall(r"<item[\s\S]*?</item>|<entry[\s\S]*?</entry>", value, flags=re.IGNORECASE)
    parts: list[str] = []
    for entry in entries[:50]:
        title = re.search(r"<title[^>]*>([\s\S]*?)</title>", entry, flags=re.IGNORECASE)
        body = re.search(
            r"<description[^>]*>([\s\S]*?)</description>|"
            r"<summary[^>]*>([\s\S]*?)</summary>|"
            r"<content[^>]*>([\s\S]*?)</content>",
            entry,
            flags=re.IGNORECASE,
        )
        body_text = next((part for part in body.groups() if part), "") if body else ""
        parts.append(_clean_html((title.group(1) if title else "") + "\n" + body_text))
    return "\n\n".join(part for part in parts if part)


class ProjectStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def setup(self) -> None:
        require_schema(self._dsn)

    @staticmethod
    def _get_with_conn(conn, project_id: str) -> dict:
        row = conn.execute(
            "SELECT project_id, created_at, updated_at, name, stage, brief, population, "
            "assumptions, decision, resolution, created_by FROM projects WHERE project_id = %s",
            (project_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"ไม่พบ project {project_id}")
        runs = conn.execute(
            "SELECT run_id, linked_at FROM project_runs WHERE project_id = %s "
            "ORDER BY linked_at DESC",
            (project_id,),
        ).fetchall()
        evidence_count = conn.execute(
            "SELECT count(*) FROM evidence_items WHERE project_id = %s", (project_id,)
        ).fetchone()[0]
        set_rows = conn.execute(
            "SELECT set_id, created_at, name, content_hash FROM evidence_sets "
            "WHERE project_id = %s ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        stage_index = PROJECT_STAGES.index(row[4])
        return {
            "project_id": row[0],
            "created_at": row[1].isoformat(),
            "updated_at": row[2].isoformat(),
            "name": row[3],
            "stage": row[4],
            "stage_index": stage_index,
            "brief": row[5],
            "population": row[6],
            "assumptions": row[7],
            "decision": row[8],
            "resolution": row[9],
            "created_by": row[10],
            "evidence_count": int(evidence_count),
            "runs": [{"run_id": item[0], "linked_at": item[1].isoformat()} for item in runs],
            "evidence_sets": [
                {
                    "set_id": item[0],
                    "created_at": item[1].isoformat(),
                    "name": item[2],
                    "content_hash": item[3],
                }
                for item in set_rows
            ],
            "workflow": [
                {
                    "stage": stage,
                    "status": (
                        "complete"
                        if index < stage_index
                        else "active"
                        if index == stage_index
                        else "pending"
                    ),
                }
                for index, stage in enumerate(PROJECT_STAGES)
            ],
        }

    def create(self, *, name: str, brief: str, actor: str) -> dict:
        project_id = f"project-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO projects (project_id, name, stage, brief, created_by) "
                "VALUES (%s, %s, 'brief', %s, %s)",
                (project_id, name.strip()[:160], brief.strip()[:20_000], actor[:160]),
            )
            snapshot = self._get_with_conn(conn, project_id)
            conn.execute(
                "INSERT INTO project_revisions (project_id, actor, snapshot) "
                "VALUES (%s, %s, %s::jsonb)",
                (project_id, actor[:160], json.dumps(snapshot, ensure_ascii=False)),
            )
        return snapshot

    def list(self, *, limit: int = 50) -> list[dict]:
        with connection(self._dsn) as conn:
            rows = conn.execute(
                "SELECT project_id, created_at, updated_at, name, stage, brief "
                "FROM projects WHERE created_by <> 'pytest' AND name NOT LIKE 'pytest %%' "
                "ORDER BY updated_at DESC LIMIT %s",
                (max(1, min(200, limit)),),
            ).fetchall()
        return [
            {
                "project_id": row[0],
                "created_at": row[1].isoformat(),
                "updated_at": row[2].isoformat(),
                "name": row[3],
                "stage": row[4],
                "brief": row[5],
            }
            for row in rows
        ]

    def get(self, project_id: str) -> dict:
        with connection(self._dsn) as conn:
            return self._get_with_conn(conn, project_id)

    def update(self, project_id: str, *, actor: str, **changes) -> dict:
        stage = changes.get("stage")
        if stage is not None and stage not in PROJECT_STAGES:
            raise ValueError("project stage ไม่ถูกต้อง")
        with connection(self._dsn) as conn:
            current = conn.execute(
                "SELECT stage FROM projects WHERE project_id = %s FOR UPDATE", (project_id,)
            ).fetchone()
            if current is None:
                raise ValueError(f"ไม่พบ project {project_id}")
            skips_stage = (
                stage is not None
                and PROJECT_STAGES.index(stage) > PROJECT_STAGES.index(current[0]) + 1
            )
            if skips_stage:
                raise ValueError("ข้าม workflow stage มากกว่าหนึ่งขั้นไม่ได้")
            population = (
                json.dumps(changes["population"], ensure_ascii=False)
                if changes.get("population") is not None
                else None
            )
            assumptions = (
                json.dumps(changes["assumptions"], ensure_ascii=False)
                if changes.get("assumptions") is not None
                else None
            )
            conn.execute(
                "UPDATE projects SET stage = COALESCE(%s, stage), brief = COALESCE(%s, brief), "
                "population = COALESCE(%s::jsonb, population), "
                "assumptions = COALESCE(%s::jsonb, assumptions), "
                "decision = COALESCE(%s, decision), resolution = COALESCE(%s, resolution), "
                "updated_at = now() WHERE project_id = %s",
                (
                    stage,
                    changes.get("brief"),
                    population,
                    assumptions,
                    changes.get("decision"),
                    changes.get("resolution"),
                    project_id,
                ),
            )
            snapshot = self._get_with_conn(conn, project_id)
            conn.execute(
                "INSERT INTO project_revisions (project_id, actor, snapshot) "
                "VALUES (%s, %s, %s::jsonb)",
                (project_id, actor[:160], json.dumps(snapshot, ensure_ascii=False)),
            )
        return snapshot

    def attach_run(self, project_id: str, run_id: str) -> None:
        with connection(self._dsn) as conn:
            if not conn.execute(
                "SELECT 1 FROM projects WHERE project_id = %s", (project_id,)
            ).fetchone():
                raise ValueError(f"ไม่พบ project {project_id}")
            conn.execute(
                "INSERT INTO project_runs (project_id, run_id) VALUES (%s, %s) "
                "ON CONFLICT (project_id, run_id) DO NOTHING",
                (project_id, run_id),
            )
            conn.execute(
                "UPDATE projects SET updated_at = now() WHERE project_id = %s", (project_id,)
            )


class EvidenceStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    @staticmethod
    def _detector() -> PIIDetector:
        if not get_settings().pii_detector_enabled:
            raise RuntimeError("PII detector ถูกปิด — evidence ingestion ถูกปฏิเสธ")
        return PIIDetector(load_allowlist())

    def preview(self, text: str) -> dict:
        report = self._detector().check(text[:MAX_EVIDENCE_CHARS])
        counts: dict[str, int] = {}
        for finding in report.findings:
            if not finding.allowlisted:
                counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return {
            "safe_to_store": not report.blocked,
            "pii_counts": counts,
            "policy": "direct-input-block; external-url-redact-and-verify",
        }

    def add_content(
        self,
        project_id: str,
        *,
        label: str,
        kind: str,
        content: str,
        actor: str,
        source_url: str = "",
        media_type: str = "text/plain",
        item_id: str = "",
        metadata: dict | None = None,
        external: bool = False,
        pii_redactions: dict | None = None,
    ) -> dict:
        detector = self._detector()
        label = label.strip()[:200]
        if not label or detector.check(label).blocked:
            raise PIIRedactionError("evidence label is empty or contains PII")
        content = content[:MAX_EVIDENCE_CHARS]
        if not content.strip():
            raise ValueError("evidence ไม่มีข้อความที่ใช้ได้")
        if external:
            redaction = detector.redact_and_verify(content)
            content = redaction.text
            pii_redactions = pii_redactions or redaction.counts
        elif detector.check(content).blocked:
            raise PIIRedactionError("direct evidence contains PII")
        status = "redacted" if pii_redactions else "ready"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        with connection(self._dsn) as conn:
            if not conn.execute(
                "SELECT 1 FROM projects WHERE project_id = %s", (project_id,)
            ).fetchone():
                raise ValueError(f"ไม่พบ project {project_id}")
            if item_id:
                item = conn.execute(
                    "SELECT project_id FROM evidence_items WHERE item_id = %s", (item_id,)
                ).fetchone()
                if item is None or item[0] != project_id:
                    raise ValueError("ไม่พบ evidence item ใน project นี้")
                version_no = conn.execute(
                    "SELECT COALESCE(max(version_no), 0) + 1 FROM evidence_versions "
                    "WHERE item_id = %s",
                    (item_id,),
                ).fetchone()[0]
            else:
                item_id = f"evidence-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
                version_no = 1
                conn.execute(
                    "INSERT INTO evidence_items "
                    "(item_id, project_id, label, kind, source_url, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (item_id, project_id, label, kind, source_url[:2000], actor[:160]),
                )
            duplicate = conn.execute(
                "SELECT v.version_id FROM evidence_versions v JOIN evidence_items i "
                "ON i.item_id = v.item_id WHERE i.project_id = %s AND v.content_hash = %s "
                "ORDER BY v.created_at LIMIT 1",
                (project_id, content_hash),
            ).fetchone()
            duplicate_of = duplicate[0] if duplicate else ""
            status = "duplicate" if duplicate else status
            version_id = f"ev-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
            conn.execute(
                "INSERT INTO evidence_versions "
                "(version_id, item_id, version_no, content, content_hash, byte_size, media_type, "
                "status, source_health, duplicate_of, pii_redactions, metadata, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)",
                (
                    version_id,
                    item_id,
                    version_no,
                    content,
                    content_hash,
                    len(content.encode()),
                    media_type[:160],
                    status,
                    "healthy" if external else "uploaded",
                    duplicate_of,
                    json.dumps(pii_redactions or {}),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    actor[:160],
                ),
            )
            conn.execute(
                "UPDATE projects SET updated_at = now() WHERE project_id = %s", (project_id,)
            )
        return self.get_version(version_id)

    def get_version(self, version_id: str, *, include_content: bool = False) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT v.version_id, v.item_id, i.project_id, i.label, i.kind, i.source_url, "
                "v.version_no, v.created_at, v.content, v.content_hash, v.byte_size, v.media_type, "
                "v.status, v.source_health, v.duplicate_of, v.pii_redactions, v.metadata "
                "FROM evidence_versions v JOIN evidence_items i ON i.item_id = v.item_id "
                "WHERE v.version_id = %s",
                (version_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"ไม่พบ evidence version {version_id}")
        result = {
            "version_id": row[0],
            "item_id": row[1],
            "project_id": row[2],
            "label": row[3],
            "kind": row[4],
            "source_url": row[5],
            "version_no": row[6],
            "created_at": row[7].isoformat(),
            "content_hash": row[9],
            "byte_size": row[10],
            "media_type": row[11],
            "status": row[12],
            "source_health": row[13],
            "duplicate_of": row[14],
            "pii_redactions": row[15],
            "metadata": row[16],
        }
        if include_content:
            result["content"] = row[8]
        return result

    def list_project(self, project_id: str) -> list[dict]:
        with connection(self._dsn) as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (i.item_id) v.version_id FROM evidence_items i "
                "JOIN evidence_versions v ON v.item_id = i.item_id "
                "WHERE i.project_id = %s ORDER BY i.item_id, v.version_no DESC",
                (project_id,),
            ).fetchall()
        return [self.get_version(row[0]) for row in rows]

    def add_url(
        self,
        project_id: str,
        *,
        label: str,
        kind: str,
        url: str,
        actor: str,
        item_id: str = "",
    ) -> dict:
        if kind not in {"url", "rss"}:
            raise ValueError("external evidence kind ต้องเป็น url หรือ rss")
        detector = self._detector()
        safe_url = validate_external_url(url)
        if detector.check(safe_url).blocked:
            raise PIIRedactionError("external evidence URL contains PII")
        response = SafeOutboundFetcher(
            max_compressed_bytes=MAX_EVIDENCE_CHARS,
            max_bytes=MAX_EVIDENCE_CHARS,
        ).fetch(safe_url)
        raw = _clean_rss(response.text) if kind == "rss" else _clean_html(response.text)
        redaction = detector.redact_and_verify(raw[:MAX_EVIDENCE_CHARS])
        return self.add_content(
            project_id,
            label=label,
            kind=kind,
            content=redaction.text,
            actor=actor,
            source_url=safe_url,
            media_type="application/rss+xml" if kind == "rss" else "text/html",
            item_id=item_id,
            metadata={
                "fetched_at": datetime.now(UTC).isoformat(),
                "host": urlparse(safe_url).hostname,
            },
            external=True,
            pii_redactions=redaction.counts,
        )

    @staticmethod
    def _manifest_members(versions: list[dict]) -> list[dict]:
        return [
            {
                key: version[key]
                for key in (
                    "version_id",
                    "item_id",
                    "label",
                    "kind",
                    "content_hash",
                    "status",
                    "pii_redactions",
                )
            }
            for version in versions
        ]

    def freeze(
        self,
        project_id: str,
        *,
        name: str,
        actor: str,
        version_ids: list[str] | None = None,
    ) -> dict:
        ids = list(dict.fromkeys(version_ids or []))
        if not ids:
            ids = [item["version_id"] for item in self.list_project(project_id)]
        if not ids:
            raise ValueError("EvidenceSetV1 ต้องมี evidence อย่างน้อยหนึ่ง version")
        versions = [self.get_version(version_id, include_content=True) for version_id in ids]
        if any(version["project_id"] != project_id for version in versions):
            raise ValueError("evidence version อยู่นอก project")
        deduplicated = []
        seen_hashes = set()
        for version in versions:
            if version["content_hash"] not in seen_hashes:
                deduplicated.append(version)
                seen_hashes.add(version["content_hash"])
        versions = deduplicated
        basis = {
            "schema_version": 1,
            "project_id": project_id,
            "members": self._manifest_members(versions),
        }
        content_hash = canonical_hash(basis)
        set_id = f"evidence-set-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        manifest = {**basis, "set_id": set_id, "content_hash": content_hash}
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO evidence_sets "
                "(set_id, project_id, schema_version, name, content_hash, manifest, created_by) "
                "VALUES (%s,%s,1,%s,%s,%s::jsonb,%s)",
                (
                    set_id,
                    project_id,
                    name.strip()[:200] or "Frozen evidence",
                    content_hash,
                    json.dumps(manifest, ensure_ascii=False),
                    actor[:160],
                ),
            )
            conn.cursor().executemany(
                "INSERT INTO evidence_set_members (set_id, version_id, ordinal) VALUES (%s,%s,%s)",
                [(set_id, version["version_id"], index) for index, version in enumerate(versions)],
            )
        return self.get_set(set_id)

    def get_set(self, set_id: str, *, include_content: bool = False) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT set_id, project_id, created_at, schema_version, name, content_hash, "
                "manifest, created_by FROM evidence_sets WHERE set_id = %s",
                (set_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ evidence set {set_id}")
            members = conn.execute(
                "SELECT version_id FROM evidence_set_members WHERE set_id = %s ORDER BY ordinal",
                (set_id,),
            ).fetchall()
        versions = [self.get_version(item[0], include_content=include_content) for item in members]
        basis = {
            "schema_version": row[3],
            "project_id": row[1],
            "members": self._manifest_members(versions),
        }
        return {
            "set_id": row[0],
            "project_id": row[1],
            "created_at": row[2].isoformat(),
            "schema_version": row[3],
            "name": row[4],
            "content_hash": row[5],
            "manifest": row[6],
            "created_by": row[7],
            "hash_valid": canonical_hash(basis) == row[5],
            "versions": versions,
        }

    def sources_for_set(self, set_id: str) -> tuple[list[dict[str, Any]], dict]:
        frozen = self.get_set(set_id, include_content=True)
        if frozen["schema_version"] != 1 or not frozen["hash_valid"]:
            raise ValueError("EvidenceSetV1 hash ไม่ถูกต้อง")
        sources = [
            {
                "kind": "text",
                "label": f"{version['label']}@v{version['version_no']}",
                "text": version["content"],
            }
            for version in frozen["versions"]
        ]
        return sources, {
            "set_id": frozen["set_id"],
            "project_id": frozen["project_id"],
            "schema_version": 1,
            "content_hash": frozen["content_hash"],
            "version_ids": [version["version_id"] for version in frozen["versions"]],
        }
