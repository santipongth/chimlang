"""PopulationSetV1 production-real trust contract."""

from copy import deepcopy
from uuid import uuid4

import pytest

from api.app import app
from core.population_store import PopulationSetStore
from simulation.persona import PersonaFactory

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม")


@needs_pg
def test_population_set_requires_explicit_synthetic_acknowledgement():
    with pytest.raises(ValueError, match="ต้องยอมรับ"):
        PopulationSetStore(DSN).freeze(
            PersonaFactory().segments,
            name="pytest population",
            actor="pytest",
            source_kind="sample-default",
            synthetic=True,
            acknowledged=False,
        )


@needs_pg
def test_population_set_is_immutable_and_hash_stable_after_input_mutation():
    segments = deepcopy(PersonaFactory().segments)
    frozen = PopulationSetStore(DSN).freeze(
        segments,
        name=f"pytest population {uuid4().hex}",
        actor="pytest",
        source_kind="sample-default",
        source_ref="pytest",
        synthetic=True,
        acknowledged=True,
    )
    segments[0]["share"] = 0.99
    loaded = PopulationSetStore(DSN).get(frozen["set_id"])

    assert loaded["hash_valid"] is True
    assert loaded["content_hash"] == frozen["content_hash"]
    assert loaded["segments"][0]["share"] != 0.99


@needs_pg
def test_population_api_and_run_fail_closed_without_acknowledgement():
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        blocked_set = client.post(
            "/population-sets",
            json={"name": "pytest blocked", "acknowledged_synthetic": False},
        )
        blocked_run = client.post(
            "/runs/async",
            json={"engine": "fabric", "subject": "ทดสอบ population gate", "agents": 20},
        )

    assert blocked_set.status_code == 422
    assert blocked_run.status_code == 422
    assert "PopulationSetV1" in blocked_run.json()["detail"]
