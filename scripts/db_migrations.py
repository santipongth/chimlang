"""Minimal idempotent DB migration runner for Chimlang.

This is intentionally lightweight: production can run this before app startup while the
project still uses module-owned schema setup. When a full migration tool is introduced,
this script becomes the compatibility bridge.
"""

from core.config import get_settings
from core.runstore import RunStore
from governance.gallery import GalleryStore
from governance.store import GovernanceStore
from governance.watchlist import WatchlistStore
from simulation.sources import setup_sources


def main() -> None:
    settings = get_settings()
    RunStore(settings.postgres_url).setup()
    GovernanceStore(settings.postgres_url).setup()
    GalleryStore(settings.postgres_url).setup()
    WatchlistStore(settings.postgres_url).setup()
    setup_sources(settings.postgres_url)
    print("database schema is up to date")


if __name__ == "__main__":
    main()
