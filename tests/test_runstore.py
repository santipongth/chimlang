from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import core.runstore as runstore


class _Result:
    def fetchone(self):
        return ("CHECK status IN (queued, running, complete, error, canceled)",)


class _Connection:
    def __init__(self, statements: list[str], statements_lock: Lock):
        self._statements = statements
        self._statements_lock = statements_lock

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement: str, params=None):
        with self._statements_lock:
            self._statements.append(statement)
        return _Result()


def test_setup_runs_schema_once_when_called_concurrently(monkeypatch):
    dsn = "postgresql://runstore-concurrency-test"
    statements: list[str] = []
    statements_lock = Lock()
    monkeypatch.setattr(runstore, "_SETUP_DONE", set())
    monkeypatch.setattr(
        runstore.RunStore,
        "_conn",
        lambda self: _Connection(statements, statements_lock),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: runstore.RunStore(dsn).setup(), range(16)))

    assert statements.count(runstore._SCHEMA) == 1
    assert sum("pg_advisory_xact_lock" in statement for statement in statements) == 1
    assert not any("DROP CONSTRAINT" in statement for statement in statements)
