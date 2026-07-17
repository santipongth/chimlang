"""Process-local PostgreSQL pool and read-only schema readiness checks.

Runtime code must never create or alter database objects.  Schema changes belong to
``scripts/db_migrations.py`` and are serialized there with one PostgreSQL advisory lock.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from psycopg import Connection
from psycopg_pool import ConnectionPool

LATEST_SCHEMA_VERSION = "2026-07-17-run-manifests-v1"


class SchemaNotReadyError(RuntimeError):
    """Raised when a process starts before the one-shot migration has completed."""


_POOLS: dict[str, ConnectionPool] = {}
_POOLS_LOCK = Lock()


def _pool_max_size() -> int:
    """Leave enough headroom for the documented 20-request concurrency check."""
    raw = os.getenv("DB_POOL_MAX_SIZE", "32")
    try:
        return max(20, min(int(raw), 64))
    except ValueError:
        return 32


def get_pool(dsn: str) -> ConnectionPool:
    """Return the pool owned by the current API/worker process."""
    pool = _POOLS.get(dsn)
    if pool is not None:
        return pool
    with _POOLS_LOCK:
        pool = _POOLS.get(dsn)
        if pool is None:
            pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=_pool_max_size(),
                timeout=10,
                open=False,
                kwargs={"connect_timeout": 5},
            )
            pool.open(wait=True)
            _POOLS[dsn] = pool
    return pool


@contextmanager
def connection(dsn: str) -> Iterator[Connection]:
    with get_pool(dsn).connection() as conn:
        yield conn


def require_schema(dsn: str, version: str = LATEST_SCHEMA_VERSION) -> None:
    """Verify the migration ledger without taking DDL locks or mutating the schema."""
    try:
        with connection(dsn) as conn:
            ledger = conn.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0]
            if ledger is None:
                raise SchemaNotReadyError("ยังไม่ได้ migrate ฐานข้อมูล: ไม่พบ schema_migrations")
            applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
            ).fetchone()
    except SchemaNotReadyError:
        raise
    except Exception as exc:
        raise SchemaNotReadyError(f"ตรวจ schema version ไม่สำเร็จ: {type(exc).__name__}") from exc
    if applied is None:
        raise SchemaNotReadyError(
            f"schema ยังไม่ถึง version {version}; รัน python -m scripts.db_migrations ก่อน"
        )


def close_pools() -> None:
    """Close pools during process shutdown and tests."""
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()
