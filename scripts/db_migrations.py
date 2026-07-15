"""Versioned idempotent DB migration runner for Chimlang.

Production can run this before app startup while the project still uses module-owned
schema setup. The ledger prevents accidental silent drift between agents/tools.
"""

from collections.abc import Callable

import psycopg

from core.config import get_settings
from core.runstore import RunStore
from governance.gallery import GalleryStore
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
