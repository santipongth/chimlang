"""Versioned idempotent DB migration runner for Chimlang.

Production can run this before app startup while the project still uses module-owned
schema setup. The ledger prevents accidental silent drift between agents/tools.
"""

import json
from collections.abc import Callable

import psycopg

from core.config import get_settings
from core.runstore import RunStore
from governance.gallery import GalleryStore
from governance.pii import PIIDetector, load_allowlist
from governance.store import GovernanceStore
from governance.watchlist import WatchlistStore
from simulation.newsdesk import setup_newsdesk
from simulation.sources import setup_sources

_LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _apply_module_schemas(dsn: str) -> None:
    RunStore(dsn).setup()
    GovernanceStore(dsn).setup()
    GalleryStore(dsn).setup()
    WatchlistStore(dsn).setup()
    setup_sources(dsn)
    setup_newsdesk(dsn)


def _apply_pii_redaction_schema(dsn: str) -> None:
    setup_sources(dsn)
    setup_newsdesk(dsn)
    detector = PIIDetector(load_allowlist())
    with psycopg.connect(dsn) as conn:
        external_rows = conn.execute(
            "SELECT url_hash, content FROM external_fetch_cache"
        ).fetchall()
        unsafe_external = [
            (key,) for key, content in external_rows if detector.check(content).blocked
        ]
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
            conn.cursor().executemany(
                "DELETE FROM news_fetch_cache WHERE cache_key = %s", unsafe_news
            )


def _scrub_legacy_pii_error_metadata(dsn: str) -> None:
    detector = PIIDetector(load_allowlist())
    with psycopg.connect(dsn) as conn:
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
            conn.cursor().executemany(
                "UPDATE run_sources SET error = %s WHERE id = %s", unsafe_sources
            )


MIGRATIONS: list[tuple[str, str, Callable[[str], None]]] = [
    (
        "2026-07-15-run-lifecycle-newsdesk-cache",
        "run lifecycle columns, source/news evidence tables, News Desk fetch cache",
        _apply_module_schemas,
    ),
    (
        "2026-07-15-run-trust-lineage-rich-evidence",
        "run lineage events, trust/readiness metadata, rich evidence source columns",
        _apply_module_schemas,
    ),
    (
        "2026-07-15-pii-redaction-before-processing",
        "redaction provenance columns and purge of unsafe external fetch caches",
        _apply_pii_redaction_schema,
    ),
    (
        "2026-07-15-scrub-legacy-pii-error-metadata",
        "remove raw PII values from legacy source and news error metadata",
        _scrub_legacy_pii_error_metadata,
    ),
]


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.postgres_url) as conn:
        conn.execute(_LEDGER)
        applied = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
    for version, description, apply in MIGRATIONS:
        if version in applied:
            print(f"skip {version}")
            continue
        apply(settings.postgres_url)
        with psycopg.connect(settings.postgres_url) as conn:
            conn.execute(
                "INSERT INTO schema_migrations (version, description) VALUES (%s, %s) "
                "ON CONFLICT (version) DO NOTHING",
                (version, description),
            )
        print(f"applied {version}")
    print("database schema is up to date")


if __name__ == "__main__":
    main()
