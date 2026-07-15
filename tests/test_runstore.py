from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import core.runstore as runstore


def test_setup_is_read_only_schema_check_when_called_concurrently(monkeypatch):
    dsn = "postgresql://runstore-concurrency-test"
    calls: list[str] = []
    lock = Lock()

    def checked(value: str) -> None:
        with lock:
            calls.append(value)

    monkeypatch.setattr(runstore, "require_schema", checked)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: runstore.RunStore(dsn).setup(), range(16)))

    assert calls == [dsn] * 16
    assert "CREATE TABLE" not in runstore.RunStore.setup.__doc__


def test_new_run_id_is_unique_across_concurrent_requests():
    with ThreadPoolExecutor(max_workers=20) as executor:
        run_ids = list(executor.map(lambda _: runstore.new_run_id("fabric"), range(100)))

    assert len(run_ids) == len(set(run_ids)) == 100
