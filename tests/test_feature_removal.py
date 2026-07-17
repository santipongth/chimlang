"""Decommissioned workspace surfaces stay absent from API and PostgreSQL."""

import pytest

from api.app import app
from api.models import RunBody

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"

REMOVED_PATH_PREFIXES = ("/projects", "/validation", "/rehearsals")
REMOVED_TABLES = (
    "projects",
    "project_revisions",
    "project_runs",
    "evidence_items",
    "evidence_versions",
    "evidence_sets",
    "evidence_set_members",
    "validation_datasets",
    "validation_cases",
    "validation_reports",
    "prediction_owner_events",
    "rehearsal_sessions",
    "rehearsal_events",
    "rehearsal_operation_leases",
)


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


def test_removed_workspaces_are_absent_from_openapi_and_run_contract():
    paths = app.openapi()["paths"]
    assert not any(path.startswith(REMOVED_PATH_PREFIXES) for path in paths)
    fields = RunBody.model_json_schema()["properties"]
    assert "project_id" not in fields
    assert "evidence_set_id" not in fields


@pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม")
def test_removed_workspace_tables_are_absent_after_migration():
    import psycopg

    with psycopg.connect(DSN) as conn:
        rows = conn.execute(
            "SELECT relname FROM pg_class WHERE relkind = 'r' AND relname = ANY(%s)",
            (list(REMOVED_TABLES),),
        ).fetchall()
    assert rows == []
