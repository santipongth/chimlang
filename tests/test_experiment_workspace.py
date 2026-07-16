from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.app import _run_dashboard, app
from api.models import RunBody
from api.services.experiments import analyze_workspace, expand_sweep, preflight_sweep
from core.config import get_settings
from core.db import connection
from core.experiment_store import ExperimentStore
from core.llm.budget import (
    MonthlyBudgetExceededError,
    check_monthly_budget,
    record_spend,
    release_budget_reservation,
    reserve_monthly_budget,
    reserved_this_month,
    spent_this_month,
)
from core.runstore import RunStore

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _pg_ok() -> bool:
    try:
        import psycopg

        psycopg.connect(DSN, connect_timeout=2).close()
        return True
    except Exception:
        return False


needs_pg = pytest.mark.skipif(not _pg_ok(), reason="PostgreSQL ไม่พร้อม")


def test_expand_sweep_is_bounded_and_rejects_parameters_with_no_effect():
    base = RunBody(engine="fabric", subject="ทดสอบ sensitivity", agents=20)
    variants = expand_sweep(base, {"seed": [1, 2], "agents": [20, 30]})
    assert len(variants) == 4
    assert {body.seed for body, _ in variants} == {1, 2}
    with pytest.raises(ValueError, match="ไม่มีผลจริง"):
        expand_sweep(base, {"rounds": [2, 3]})
    with pytest.raises(ValueError, match="12 variants"):
        expand_sweep(base, {"seed": list(range(13))})


def test_preflight_sweep_uses_aggregate_cost_before_enqueue(monkeypatch):
    import api.services.experiments as service

    variants = [
        (RunBody(engine="debate", subject="ทดสอบงบ", agents=10), {"seed": seed})
        for seed in (1, 2, 3)
    ]
    monkeypatch.setattr(
        service,
        "estimate_run_cost",
        lambda body: {"estimated_usd": 0.4, "run_cap_usd": 5.0},
    )
    monkeypatch.setattr(service, "spent_this_month", lambda dsn: 1.0)
    result = preflight_sweep(variants, monthly_cap=3.0)
    assert result["estimated_usd"] == pytest.approx(1.2)
    with pytest.raises(RuntimeError, match="งบรวมเดือน"):
        preflight_sweep(variants, monthly_cap=2.0)


@needs_pg
def test_monthly_budget_reservation_is_atomic_and_settles_actual_spend():
    reservation_id = f"test-reservation-{uuid4()}"
    competing_id = f"test-reservation-{uuid4()}"
    run_id = f"test-reservation-spend-{uuid4()}"
    baseline = spent_this_month(DSN) + reserved_this_month(DSN)
    try:
        reserved = reserve_monthly_budget(
            DSN,
            {reservation_id: 0.2},
            baseline + 0.25,
            context="pytest",
        )
        assert reserved == pytest.approx(0.2)
        with pytest.raises(MonthlyBudgetExceededError):
            reserve_monthly_budget(
                DSN,
                {competing_id: 0.1},
                baseline + 0.25,
                context="pytest",
            )
        record_spend(
            DSN,
            0.05,
            run_id=run_id,
            reservation_id=reservation_id,
        )
        with connection(DSN) as conn:
            remaining = conn.execute(
                "SELECT usd_remaining FROM monthly_budget_reservations WHERE reservation_id = %s",
                (reservation_id,),
            ).fetchone()[0]
        assert float(remaining) == pytest.approx(0.15)
        assert release_budget_reservation(DSN, reservation_id) == pytest.approx(0.15)
        check_monthly_budget(
            DSN,
            0.1,
            baseline + 0.25,
            reservation_id=reservation_id,
        )
        with connection(DSN) as conn:
            reused = conn.execute(
                "SELECT usd_remaining FROM monthly_budget_reservations WHERE reservation_id = %s",
                (reservation_id,),
            ).fetchone()[0]
        assert float(reused) == pytest.approx(0.1)
    finally:
        release_budget_reservation(DSN, reservation_id)
        release_budget_reservation(DSN, competing_id)
        with connection(DSN) as conn:
            conn.execute("DELETE FROM llm_spend WHERE run_id = %s", (run_id,))
            conn.execute(
                "DELETE FROM monthly_budget_reservations WHERE reservation_id IN (%s, %s)",
                (reservation_id, competing_id),
            )


def test_fabric_persistent_seed_changes_multiverse_snapshot():
    first = _run_dashboard("ทดสอบ seed experiment", "aggregate", 20, base_seed=11)
    second = _run_dashboard("ทดสอบ seed experiment", "aggregate", 20, base_seed=12)
    assert first.universe_estimates != second.universe_estimates


@needs_pg
def test_workspace_analysis_compares_arbitrary_runs_and_ranks_sensitivity():
    run_store = RunStore(DSN)
    exp_store = ExperimentStore(DSN)
    experiment_id = exp_store.create(
        name="ทดสอบ arbitrary comparison",
        kind="sweep",
        base_config={"engine": "debate"},
        dimensions={"seed": [1, 2]},
        created_by="test",
    )
    run_ids = [f"exp-analysis-{uuid4()}" for _ in range(2)]
    try:
        for index, run_id in enumerate(run_ids):
            run_store.create(
                run_id=run_id,
                engine="debate",
                subject="ทดสอบ sensitivity",
                domain="ทั่วไป",
                agents=2,
                rounds=1,
                seed=index + 1,
                config={"experiment_id": experiment_id},
            )
            run_store.finish(
                run_id,
                {
                    "metrics": {"per_round_avg_stance": [(-0.4, 0.6)[index]]},
                    "cost_usd": 0.01,
                },
            )
            exp_store.add_member(experiment_id, run_id, {"seed": index + 1})
        workspace = exp_store.get(experiment_id)
        analysis = analyze_workspace(DSN, workspace)
        assert analysis["completed"] == 2
        assert analysis["total_cost_usd"] == pytest.approx(0.02)
        assert analysis["dimensions"]["seed"]["sensitivity_range"] == pytest.approx(1.0)
        assert analysis["ranked_sensitivity"][0]["parameter"] == "seed"
        assert analysis["public_votes_used"] is False
    finally:
        for run_id in run_ids:
            try:
                run_store.delete(run_id)
            except ValueError:
                pass
        exp_store.delete(experiment_id)


@needs_pg
def test_comparison_api_accepts_existing_runs_only():
    client = TestClient(app)
    run_store = RunStore(DSN)
    run_ids = [f"exp-api-{uuid4()}" for _ in range(2)]
    experiment_id = ""
    try:
        for index, run_id in enumerate(run_ids):
            run_store.create(
                run_id=run_id,
                engine="fabric",
                subject="ทดสอบ comparison API",
                domain="ทั่วไป",
                agents=20,
                rounds=20,
                seed=index,
                config={},
            )
            run_store.finish(run_id, {"brief": {"headline_range": [index, index + 0.2]}})
        response = client.post(
            "/experiments/compare",
            json={"name": "เทียบ run ที่เลือก", "run_ids": run_ids},
        )
        assert response.status_code == 200
        payload = response.json()
        experiment_id = payload["workspace"]["experiment_id"]
        assert payload["analysis"]["completed"] == 2
        assert payload["analysis"]["public_votes_used"] is False
        assert client.get(f"/experiments/{experiment_id}").status_code == 200
    finally:
        if experiment_id:
            ExperimentStore(get_settings().postgres_url).delete(experiment_id)
        for run_id in run_ids:
            try:
                run_store.delete(run_id)
            except ValueError:
                pass


@needs_pg
def test_sweep_api_preflights_all_variants_before_queue(monkeypatch):
    import api.app as app_module
    import api.routers.experiments as router_module

    jobs = []

    def fake_queue(body, principal, *, preallocated_run_id=None):
        run_id = preallocated_run_id or f"sweep-fake-{len(jobs)}"
        jobs.append((run_id, body))
        return {"job_id": f"job-{len(jobs)}", "run_id": run_id, "status": "PENDING"}

    monkeypatch.setattr(app_module, "_enqueue_persistent_run", fake_queue)
    monkeypatch.setattr(
        router_module,
        "preflight_sweep",
        lambda variants, cap: {"variants": len(variants), "estimated_usd": 0.0},
    )
    client = TestClient(app)
    response = client.post(
        "/experiments/sweep",
        json={
            "name": "seed sweep",
            "base_run": {"engine": "fabric", "subject": "ทดสอบ sweep", "agents": 20},
            "parameters": {"seed": [1, 2]},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["budget"]["variants"] == 2
    assert len(jobs) == 2
    assert all(body.experiment_id == payload["experiment_id"] for _, body in jobs)
    ExperimentStore(DSN).delete(payload["experiment_id"])
