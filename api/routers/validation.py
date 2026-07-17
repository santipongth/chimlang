"""Validation Lab, human-panel import, and resolution inbox APIs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_principal, require
from api.models import ApiError
from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, TierLoad
from core.llm.budget import check_monthly_budget
from core.llm.userconfig import effective_llm_settings, effective_monthly_cap, effective_pricing
from core.validation_store import ValidationStore
from governance.rbac import Permission, Principal

router = APIRouter(prefix="/validation", tags=["validation"])


class HumanPanelCase(BaseModel):
    case_id: str = Field(default="", max_length=160)
    prompt: str = Field(min_length=1, max_length=20_000)
    expected: Any
    observed: dict[str, Any] = Field(default_factory=dict)
    slice: dict[str, Any] = Field(default_factory=dict)


class HumanPanelImportBody(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    consent_confirmed: bool
    consent_basis: str = Field(min_length=1, max_length=2_000)
    collected_at: datetime
    rows: list[HumanPanelCase] = Field(min_length=1, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationDatasetResponse(BaseModel):
    dataset_id: str
    created_at: str
    kind: str
    name: str
    revision: str
    license: str
    content_hash: str
    metadata: dict[str, Any]
    created_by: str
    case_count: int


class ValidationReportResponse(BaseModel):
    report_id: str
    dataset_id: str
    created_at: str
    kind: str
    metrics: dict[str, Any]
    raw_result_hash: str
    metadata: dict[str, Any]
    created_by: str
    trust_status: str


class ValidationOverviewResponse(BaseModel):
    datasets: list[ValidationDatasetResponse]
    reports: list[ValidationReportResponse]
    trust_claims: dict[str, bool]


class OwnerAssignBody(BaseModel):
    owner: str = Field(min_length=1, max_length=160)


class OwnerAssignResponse(BaseModel):
    prediction_id: int
    owner: str
    assigned_at: str
    actor: str


class ResolutionInboxResponse(BaseModel):
    as_of: str
    due: list[dict[str, Any]]
    upcoming: list[dict[str, Any]]
    resolved: list[dict[str, Any]]
    metrics: dict[str, Any]
    resolution_requires_evidence: bool


class RobustnessPreflightBody(BaseModel):
    models: list[str] = Field(min_length=2, max_length=3)
    sample_size: int = Field(ge=1, le=200)
    avg_input_tokens: int = Field(default=1200, ge=100, le=20_000)
    avg_output_tokens: int = Field(default=400, ge=50, le=4_000)


class RobustnessPreflightResponse(BaseModel):
    models: list[str]
    sample_size: int
    estimated_usd: float
    breakdown: dict[str, float]
    run_cap_usd: float
    monthly_cap_usd: float
    opt_in_required: bool
    execution_started: bool


def _store() -> ValidationStore:
    return ValidationStore(get_settings().postgres_url)


@router.get("/overview", response_model=ValidationOverviewResponse)
def validation_overview(principal: Principal = Depends(get_principal)) -> dict:
    datasets = _store().list_datasets()
    reports = _store().list_reports()
    return {
        "datasets": datasets,
        "reports": reports,
        "trust_claims": {
            "miracl_measured": any(
                item["kind"] == "miracl_retrieval" and item["trust_status"] == "measured"
                for item in reports
            ),
            "human_panel_measured": any(item["kind"] == "human_panel" for item in reports),
            "pilot_usability_measured": any(item["kind"] == "usability" for item in reports),
        },
    }


@router.post(
    "/datasets/human-panel",
    status_code=201,
    response_model=ValidationDatasetResponse,
    responses={422: {"model": ApiError}},
)
def import_human_panel(
    body: HumanPanelImportBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    collected_at = (
        body.collected_at
        if body.collected_at.tzinfo is not None
        else body.collected_at.replace(tzinfo=UTC)
    )
    if collected_at > datetime.now(UTC):
        raise HTTPException(status_code=422, detail="collected_at ต้องไม่อยู่ในอนาคต")
    try:
        return _store().import_human_panel(
            name=body.name,
            consent_confirmed=body.consent_confirmed,
            consent_basis=body.consent_basis,
            collected_at=collected_at,
            rows=[row.model_dump() for row in body.rows],
            metadata=body.metadata,
            actor=principal.user_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/resolution-inbox", response_model=ResolutionInboxResponse)
def resolution_inbox(principal: Principal = Depends(get_principal)) -> dict:
    return _store().resolution_inbox(date.today())


@router.post(
    "/predictions/{prediction_id}/owner",
    status_code=201,
    response_model=OwnerAssignResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def assign_resolution_owner(
    prediction_id: int,
    body: OwnerAssignBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    try:
        return _store().assign_owner(prediction_id, owner=body.owner, actor=principal.user_id)
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post(
    "/robustness/preflight",
    response_model=RobustnessPreflightResponse,
    responses={422: {"model": ApiError}},
)
def robustness_preflight(
    body: RobustnessPreflightBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    models = list(dict.fromkeys(model.strip() for model in body.models if model.strip()))
    if len(models) < 2:
        raise HTTPException(status_code=422, detail="ต้องมี model ไม่ซ้ำ 2-3 รุ่น")
    settings = effective_llm_settings()
    pricing = effective_pricing()
    try:
        estimate = CostEstimator(pricing).estimate(
            [
                TierLoad(
                    model,
                    body.sample_size,
                    body.avg_input_tokens,
                    body.avg_output_tokens,
                )
                for model in models
            ]
        )
        guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
        guard.check_estimate(estimate)
        check_monthly_budget(
            settings.postgres_url,
            estimate.total_usd,
            effective_monthly_cap(),
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "models": models,
        "sample_size": body.sample_size,
        "estimated_usd": round(estimate.total_usd, 6),
        "breakdown": {model: round(cost, 6) for model, cost in estimate.breakdown.items()},
        "run_cap_usd": settings.run_budget_usd_cap,
        "monthly_cap_usd": effective_monthly_cap(),
        "opt_in_required": True,
        "execution_started": False,
    }
