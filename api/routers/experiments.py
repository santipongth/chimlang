"""Experiment workspace API — thin routing over deterministic services."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_principal, require
from api.models import RunBody
from api.services.experiments import analyze_workspace, expand_sweep, preflight_sweep
from core.config import get_settings
from core.experiment_store import ExperimentStore
from core.llm.budget import release_budget_reservation, reserve_monthly_budget
from core.llm.userconfig import effective_monthly_cap
from core.runstore import RunStore, new_run_id
from governance.rbac import Permission, Principal

router = APIRouter(prefix="/experiments", tags=["experiments"])


class SweepBody(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    base_run: RunBody
    parameters: dict[str, list]


class ComparisonBody(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    run_ids: list[str] = Field(min_length=2, max_length=12)


def _store() -> ExperimentStore:
    return ExperimentStore(get_settings().postgres_url)


@router.get("")
def list_experiments(
    limit: int = Query(50, ge=1, le=200), principal: Principal = Depends(get_principal)
) -> dict:
    return {"experiments": _store().list(limit=limit)}


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        workspace = _store().get(experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    analysis = analyze_workspace(get_settings().postgres_url, workspace)
    return {"workspace": workspace, "analysis": analysis}


@router.post("/compare")
def create_comparison(body: ComparisonBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    run_store = RunStore(get_settings().postgres_url)
    unique_ids = list(dict.fromkeys(body.run_ids))
    if len(unique_ids) < 2:
        raise HTTPException(status_code=422, detail="comparison ต้องมี run ไม่ซ้ำอย่างน้อย 2 รายการ")
    try:
        for run_id in unique_ids:
            run_store.get(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store = _store()
    experiment_id = store.create(
        name=body.name,
        kind="comparison",
        base_config={},
        dimensions={},
        created_by=principal.user_id,
    )
    for run_id in unique_ids:
        store.add_member(experiment_id, run_id, {})
    return get_experiment(experiment_id, principal)


@router.post("/sweep")
def create_sweep(body: SweepBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    try:
        variants = expand_sweep(body.base_run, body.parameters)
        monthly_cap = effective_monthly_cap()
        budget = preflight_sweep(variants, monthly_cap)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_ids = [new_run_id(run_body.engine) for run_body, _ in variants]
    estimates = budget.get("variant_estimates_usd") or [0.0] * len(variants)
    reservations = {
        run_id: float(estimate)
        for run_id, estimate in zip(run_ids, estimates, strict=True)
        if float(estimate) > 0
    }
    try:
        reserve_monthly_budget(
            get_settings().postgres_url,
            reservations,
            monthly_cap,
            context="experiment_sweep",
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store = _store()
    try:
        experiment_id = store.create(
            name=body.name,
            kind="sweep",
            base_config=body.base_run.model_dump(),
            dimensions=body.parameters,
            created_by=principal.user_id,
        )
    except Exception:
        for run_id in reservations:
            release_budget_reservation(get_settings().postgres_url, run_id)
        raise
    jobs = []
    # Import at request time to keep the router independent from app construction.
    from api.app import _enqueue_persistent_run

    for index, (run_body, variant) in enumerate(variants):
        run_id = run_ids[index]
        queued_body = run_body.model_copy(update={"experiment_id": experiment_id})
        try:
            result = _enqueue_persistent_run(
                queued_body,
                principal,
                preallocated_run_id=run_id,
            )
        except Exception:
            for pending_run_id in run_ids[index:]:
                release_budget_reservation(get_settings().postgres_url, pending_run_id)
            raise
        store.add_member(experiment_id, run_id, variant)
        jobs.append({"run_id": run_id, "job_id": result.get("job_id"), "variant": variant})
    return {
        "experiment_id": experiment_id,
        "budget": budget,
        "jobs": jobs,
        "public_votes_used": False,
    }


@router.delete("/{experiment_id}")
def delete_experiment(experiment_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    if not _store().delete(experiment_id):
        raise HTTPException(status_code=404, detail="ไม่พบ experiment")
    return {"deleted": True, "experiment_id": experiment_id}
