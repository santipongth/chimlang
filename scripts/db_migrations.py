"""Versioned Chimlang migrations, serialized by one PostgreSQL advisory lock.

This module is the only production path allowed to execute DDL. API and Celery
processes perform a read-only ledger check and fail closed when this runner has not
finished.
"""

import json
from collections.abc import Callable

import psycopg
from psycopg import Connection

from core.config import get_settings
from governance.pii import PIIDetector, load_allowlist

MIGRATION_LOCK = "chimlang:schema-migrations:v2"

_LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _apply_module_schemas(conn: Connection) -> None:
    """Bootstrap a fresh database from every PostgreSQL-owned module schema."""
    from core.appsettings import _SCHEMA as appsettings_schema
    from core.experiment_store import _SCHEMA as experiment_schema
    from core.llm.budget import _SCHEMA as budget_schema
    from core.runstore import _SCHEMA as runstore_schema
    from governance.gallery import _SCHEMA as gallery_schema
    from governance.store import _SCHEMA as governance_schema
    from governance.watchlist import _SCHEMA as watchlist_schema
    from simulation.memory import _SCHEMA as memory_schema
    from simulation.newsdesk import _SCHEMA as newsdesk_schema
    from simulation.persona_packs import _SCHEMA as packs_schema
    from simulation.sources import _SCHEMA as sources_schema

    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for schema in (
        runstore_schema,
        governance_schema,
        gallery_schema,
        watchlist_schema,
        packs_schema,
        sources_schema,
        newsdesk_schema,
        memory_schema,
        appsettings_schema,
        budget_schema,
        experiment_schema,
    ):
        conn.execute(schema)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS citizen_feedback ("
        "id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "segment_id TEXT NOT NULL, stance TEXT NOT NULL)"
    )


def _apply_rich_evidence_schema(conn: Connection) -> None:
    conn.execute(
        "ALTER TABLE run_sources ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE run_sources ADD COLUMN IF NOT EXISTS duplicate_of TEXT NOT NULL DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE run_sources ADD COLUMN IF NOT EXISTS quality_score "
        "DOUBLE PRECISION NOT NULL DEFAULT 0"
    )


def _apply_pii_redaction_schema(conn: Connection) -> None:
    conn.execute(
        "ALTER TABLE run_sources ADD COLUMN IF NOT EXISTS pii_redactions "
        "JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    conn.execute(
        "ALTER TABLE external_fetch_cache ADD COLUMN IF NOT EXISTS pii_redactions "
        "JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    conn.execute(
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS pii_redactions "
        "JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    detector = PIIDetector(load_allowlist())
    external_rows = conn.execute("SELECT url_hash, content FROM external_fetch_cache").fetchall()
    unsafe_external = [(key,) for key, content in external_rows if detector.check(content).blocked]
    if unsafe_external:
        conn.cursor().executemany(
            "DELETE FROM external_fetch_cache WHERE url_hash = %s", unsafe_external
        )
    news_rows = conn.execute("SELECT cache_key, payload FROM news_fetch_cache").fetchall()
    unsafe_news = [
        (key,)
        for key, payload in news_rows
        if detector.check(json.dumps(payload, ensure_ascii=False)).blocked
    ]
    if unsafe_news:
        conn.cursor().executemany("DELETE FROM news_fetch_cache WHERE cache_key = %s", unsafe_news)


def _scrub_legacy_pii_error_metadata(conn: Connection | str) -> None:
    if isinstance(conn, str):
        with psycopg.connect(conn) as opened:
            _scrub_legacy_pii_error_metadata(opened)
        return
    detector = PIIDetector(load_allowlist())
    news_rows = conn.execute("SELECT id, error FROM news_items WHERE error <> ''").fetchall()
    unsafe_news = [
        ("พบ PII (GOV-01) — legacy metadata scrubbed", row_id)
        for row_id, error in news_rows
        if detector.check(error).blocked
    ]
    if unsafe_news:
        conn.cursor().executemany("UPDATE news_items SET error = %s WHERE id = %s", unsafe_news)
    source_rows = conn.execute("SELECT id, error FROM run_sources WHERE error <> ''").fetchall()
    unsafe_sources = [
        ("พบ PII (GOV-01) — legacy metadata scrubbed", row_id)
        for row_id, error in source_rows
        if detector.check(error).blocked
    ]
    if unsafe_sources:
        conn.cursor().executemany("UPDATE run_sources SET error = %s WHERE id = %s", unsafe_sources)


def _apply_runtime_and_prediction_experience(conn: Connection) -> None:
    conn.execute(
        """
        ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
        ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS attempt INT NOT NULL DEFAULT 0;
        ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS idempotency_key TEXT NOT NULL DEFAULT '';
        CREATE UNIQUE INDEX IF NOT EXISTS sim_runs_idempotency_key
            ON sim_runs (idempotency_key) WHERE idempotency_key <> '';

        ALTER TABLE run_events ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT '';
        ALTER TABLE run_events ADD COLUMN IF NOT EXISTS progress INT;
        ALTER TABLE run_events ADD COLUMN IF NOT EXISTS call_status TEXT NOT NULL DEFAULT '';
        ALTER TABLE run_events ADD COLUMN IF NOT EXISTS cost_usd DOUBLE PRECISION;
        CREATE INDEX IF NOT EXISTS run_events_replay ON run_events (run_id, id);

        CREATE TABLE IF NOT EXISTS run_synthesis_revisions (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            kind TEXT NOT NULL CHECK (kind IN ('analyst', 'mechanical')),
            synthesis JSONB NOT NULL,
            metrics JSONB NOT NULL DEFAULT '{}',
            model_version TEXT NOT NULL DEFAULT '',
            parser_mode TEXT NOT NULL DEFAULT '',
            cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS run_synthesis_revisions_run
            ON run_synthesis_revisions (run_id, id);

        CREATE TABLE IF NOT EXISTS simulation_findings (
            id BIGSERIAL PRIMARY KEY,
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            run_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            metrics JSONB NOT NULL DEFAULT '{}',
            provenance JSONB NOT NULL DEFAULT '{}',
            model_version TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS simulation_findings_run ON simulation_findings (run_id, id);

        ALTER TABLE prediction_registry ADD COLUMN IF NOT EXISTS source_kind TEXT
            NOT NULL DEFAULT 'legacy';
        ALTER TABLE prediction_registry ADD COLUMN IF NOT EXISTS forecast_type TEXT
            NOT NULL DEFAULT 'binary';
        ALTER TABLE prediction_registry ADD COLUMN IF NOT EXISTS provenance JSONB
            NOT NULL DEFAULT '{}';
        ALTER TABLE prediction_registry ADD COLUMN IF NOT EXISTS created_by TEXT
            NOT NULL DEFAULT '';

        ALTER TABLE prediction_resolution ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ;
        ALTER TABLE prediction_resolution ADD COLUMN IF NOT EXISTS evidence_url TEXT
            NOT NULL DEFAULT '';
        ALTER TABLE prediction_resolution ADD COLUMN IF NOT EXISTS evidence_name TEXT
            NOT NULL DEFAULT '';
        """
    )


def _apply_structured_output_schema(conn: Connection) -> None:
    conn.execute(
        "ALTER TABLE debate_posts ADD COLUMN IF NOT EXISTS parser_mode TEXT NOT NULL DEFAULT ''"
    )
    # Existing rows remain physically untouched and read as legacy via the new default.
    conn.execute(
        """
        DROP TRIGGER IF EXISTS run_synthesis_revisions_append_only ON run_synthesis_revisions;
        CREATE TRIGGER run_synthesis_revisions_append_only
            BEFORE UPDATE OR DELETE ON run_synthesis_revisions
            FOR EACH ROW EXECUTE FUNCTION reject_mutation();
        DROP TRIGGER IF EXISTS simulation_findings_append_only ON simulation_findings;
        CREATE TRIGGER simulation_findings_append_only
            BEFORE UPDATE OR DELETE ON simulation_findings
            FOR EACH ROW EXECUTE FUNCTION reject_mutation();
        """
    )


def _retain_synthesis_revisions(conn: Connection) -> None:
    conn.execute(
        "ALTER TABLE run_synthesis_revisions "
        "DROP CONSTRAINT IF EXISTS run_synthesis_revisions_run_id_fkey"
    )


def _apply_typed_debate_moves(conn: Connection) -> None:
    conn.execute(
        """
        ALTER TABLE debate_posts ADD COLUMN IF NOT EXISTS move_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE debate_posts ADD COLUMN IF NOT EXISTS move_type TEXT NOT NULL DEFAULT 'claim';
        ALTER TABLE debate_posts ADD COLUMN IF NOT EXISTS parent_move_id TEXT NOT NULL DEFAULT '';
        ALTER TABLE debate_posts ADD COLUMN IF NOT EXISTS evidence_refs JSONB
            NOT NULL DEFAULT '[]'::jsonb;
        CREATE UNIQUE INDEX IF NOT EXISTS debate_posts_move_id
            ON debate_posts (run_id, move_id) WHERE move_id <> '';
        CREATE INDEX IF NOT EXISTS debate_posts_parent_move
            ON debate_posts (run_id, parent_move_id) WHERE parent_move_id <> '';
        """
    )


def _apply_vector_retrieval_and_observability(conn: Connection) -> None:
    from core.observability import _SCHEMA as observability_schema

    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_chunk_embeddings (
            chunk_id BIGINT NOT NULL REFERENCES run_chunks(id) ON DELETE CASCADE,
            run_id TEXT NOT NULL,
            model TEXT NOT NULL,
            model_version TEXT NOT NULL,
            dimension INT NOT NULL,
            embedding vector NOT NULL,
            embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (chunk_id, model, dimension)
        );
        CREATE INDEX IF NOT EXISTS run_chunk_embeddings_run
            ON run_chunk_embeddings (run_id, model, dimension);
        CREATE INDEX IF NOT EXISTS run_chunk_embeddings_hnsw_1536
            ON run_chunk_embeddings USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
            WHERE dimension = 1536;
        """
    )
    conn.execute(observability_schema)


def _apply_experiment_workspaces(conn: Connection) -> None:
    from core.experiment_store import _SCHEMA as experiment_schema

    conn.execute(experiment_schema)


def _apply_monthly_budget_reservations(conn: Connection) -> None:
    from core.llm.budget import _SCHEMA as budget_schema

    conn.execute(budget_schema)


def _apply_run_manifests_v1(conn: Connection) -> None:
    conn.execute(
        """
        ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS idempotency_request_hash TEXT
            NOT NULL DEFAULT '';
        CREATE TABLE IF NOT EXISTS run_manifests (
            run_id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            schema_version INT NOT NULL,
            complete BOOLEAN NOT NULL,
            config_hash TEXT NOT NULL,
            manifest_hash TEXT NOT NULL,
            reproducibility TEXT NOT NULL,
            spec JSONB NOT NULL DEFAULT '{}'::jsonb,
            manifest JSONB NOT NULL
        );
        INSERT INTO run_manifests (
            run_id, schema_version, complete, config_hash, manifest_hash,
            reproducibility, spec, manifest
        )
        SELECT
            run_id, 0, false, '', '', 'legacy-incomplete', '{}'::jsonb,
            jsonb_build_object(
                'run_id', run_id,
                'schema_version', 0,
                'complete', false,
                'reproducibility', 'legacy-incomplete',
                'reason', 'created-before-ADR-0014; provenance was not reconstructed'
            )
        FROM sim_runs
        ON CONFLICT (run_id) DO NOTHING;
        DROP TRIGGER IF EXISTS run_manifests_append_only ON run_manifests;
        CREATE TRIGGER run_manifests_append_only
            BEFORE UPDATE OR DELETE ON run_manifests
            FOR EACH ROW EXECUTE FUNCTION reject_mutation();
        """
    )


def _apply_project_evidence_v1(conn: Connection) -> None:
    from core.project_store import _SCHEMA as project_schema

    conn.execute(project_schema)


def _apply_validation_lab_v1(conn: Connection) -> None:
    from core.validation_store import _SCHEMA as validation_schema

    conn.execute(validation_schema)


def _apply_rehearsal_sessions_v1(conn: Connection) -> None:
    from core.rehearsal_store import _SCHEMA as rehearsal_schema

    conn.execute(rehearsal_schema)


def _apply_rehearsal_leases_v1(conn: Connection) -> None:
    from core.rehearsal_store import _SCHEMA as rehearsal_schema

    conn.execute(rehearsal_schema)


def _apply_validation_case_kinds_v1(conn: Connection) -> None:
    conn.execute(
        """
        ALTER TABLE validation_datasets
            DROP CONSTRAINT IF EXISTS validation_datasets_kind_check;
        ALTER TABLE validation_datasets
            ADD CONSTRAINT validation_datasets_kind_check
            CHECK (kind IN ('miracl_th','human_panel','model_robustness','usability'));
        """
    )


Migration = tuple[str, str, Callable[[Connection], None]]

MIGRATIONS: list[Migration] = [
    (
        "2026-07-15-run-lifecycle-newsdesk-cache",
        "bootstrap all module schemas and run lifecycle/news cache",
        _apply_module_schemas,
    ),
    (
        "2026-07-15-run-trust-lineage-rich-evidence",
        "run lineage, trust metadata and rich evidence columns",
        _apply_rich_evidence_schema,
    ),
    (
        "2026-07-15-pii-redaction-before-processing",
        "redaction provenance columns and unsafe cache purge",
        _apply_pii_redaction_schema,
    ),
    (
        "2026-07-15-scrub-legacy-pii-error-metadata",
        "remove raw PII values from legacy error metadata",
        _scrub_legacy_pii_error_metadata,
    ),
    (
        "2026-07-15-prediction-experience-v1",
        "runtime heartbeat/events plus finding/prediction/synthesis contracts",
        _apply_runtime_and_prediction_experience,
    ),
    (
        "2026-07-15-structured-output-v1",
        "structured-output parser provenance for debate posts",
        _apply_structured_output_schema,
    ),
    (
        "2026-07-15-synthesis-revision-retention-v1",
        "retain append-only synthesis revisions after operational run deletion",
        _retain_synthesis_revisions,
    ),
    (
        "2026-07-16-typed-debate-moves-v1",
        "typed debate moves with evidence and parent lineage",
        _apply_typed_debate_moves,
    ),
    (
        "2026-07-16-vector-retrieval-observability-v1",
        "pgvector HNSW evidence index and PII-safe provider telemetry",
        _apply_vector_retrieval_and_observability,
    ),
    (
        "2026-07-16-experiment-workspaces-v1",
        "operational sweep/comparison workspaces with run membership",
        _apply_experiment_workspaces,
    ),
    (
        "2026-07-16-monthly-budget-reservations-v1",
        "transactional monthly budget reservations before sweep enqueue",
        _apply_monthly_budget_reservations,
    ),
    (
        "2026-07-17-run-manifests-v1",
        "immutable run specs/manifests and idempotent async request hashes",
        _apply_run_manifests_v1,
    ),
    (
        "2026-07-17-project-evidence-v1",
        "project workflow, append-only evidence versions and immutable evidence sets",
        _apply_project_evidence_v1,
    ),
    (
        "2026-07-17-validation-lab-v1",
        "append-only validation datasets/reports and resolution ownership",
        _apply_validation_lab_v1,
    ),
    (
        "2026-07-17-rehearsal-sessions-v1",
        "event-sourced rehearsal sessions, checkpoints and decision logs",
        _apply_rehearsal_sessions_v1,
    ),
    (
        "2026-07-17-rehearsal-leases-v1",
        "expiring operation leases prevent duplicate rehearsal provider calls",
        _apply_rehearsal_leases_v1,
    ),
    (
        "2026-07-17-validation-case-kinds-v1",
        "append-only model robustness and usability validation dataset kinds",
        _apply_validation_case_kinds_v1,
    ),
]


def migrate(dsn: str) -> list[str]:
    """Apply pending versions under one session-level advisory lock."""
    applied_now: list[str] = []
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (MIGRATION_LOCK,))
        try:
            with conn.transaction():
                conn.execute(_LEDGER)
            for version, description, apply in MIGRATIONS:
                row = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
                ).fetchone()
                if row is not None:
                    continue
                with conn.transaction():
                    apply(conn)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (%s, %s)",
                        (version, description),
                    )
                applied_now.append(version)
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (MIGRATION_LOCK,))
    return applied_now


def main() -> None:
    applied = migrate(get_settings().postgres_url)
    for version in applied:
        print(f"applied {version}")
    if not applied:
        print("skip: database schema is already current")
    print("database schema is up to date")


if __name__ == "__main__":
    main()
