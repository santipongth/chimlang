"""Experiment workspace API — thin routing over deterministic services."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_principal, require
from api.models import RunBody
from api.services.experiments import analyze_workspace, expand_sweep, preflight_sweep
from core.config import get_settings
from core.experiment_store import ExperimentStore
from core.llm.userconfig import effective_monthly_cap
from core.runstore import RunStore
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
        budget = preflight_sweep(variants, effective_monthly_cap())
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store = _store()
    experiment_id = store.create(
        name=body.name,
        kind="sweep",
        base_config=body.base_run.model_dump(),
        dimensions=body.parameters,
        created_by=principal.user_id,
    )
    jobs = []
    # Import at request time to keep the router independent from app construction.
    from api.app import run_create_async

    for run_body, variant in variants:
        queued_body = run_body.model_copy(update={"experiment_id": experiment_id})
        result = run_create_async(queued_body, principal)
        run_id = str(result.get("run_id") or (result.get("result") or {}).get("run_id") or "")
        if not run_id:
            raise HTTPException(status_code=503, detail="queue ไม่คืน run_id สำหรับ experiment")
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
