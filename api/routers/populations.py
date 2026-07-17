"""Immutable PopulationSetV1 API."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_principal, require
from api.models import ApiError
from core.config import get_settings
from core.population_store import PopulationSetStore
from core.project_store import ProjectStore
from governance.rbac import Permission, Principal
from simulation.persona import PersonaFactory

router = APIRouter(prefix="/population-sets", tags=["populations"])


class PopulationFreezeBody(BaseModel):
    name: str = Field(default="Frozen population", max_length=200)
    pack_id: int | None = None
    project_id: str = ""
    acknowledged_synthetic: bool = False


class PopulationSetResponse(BaseModel):
    set_id: str
    project_id: str
    created_at: str
    schema_version: int
    name: str
    source_kind: str
    source_ref: str
    synthetic: bool
    acknowledged: bool
    content_hash: str
    manifest: dict[str, Any]
    created_by: str
    hash_valid: bool
    segments: list[dict[str, Any]]


def _segments(pack_id: int | None) -> tuple[list[dict], str, str]:
    if pack_id is None:
        return PersonaFactory().segments, "sample-default", "data/samples/population/segments.yaml"
    from simulation.persona_packs import PackStore

    pack = PackStore(get_settings().postgres_url).get(pack_id)
    return pack.segments, "persona-pack", str(pack.id)


@router.post(
    "",
    status_code=201,
    response_model=PopulationSetResponse,
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def freeze_population(
    body: PopulationFreezeBody, principal: Principal = Depends(get_principal)
) -> dict:
    require(principal, Permission.RUN)
    try:
        if body.project_id:
            ProjectStore(get_settings().postgres_url).get(body.project_id)
        segments, source_kind, source_ref = _segments(body.pack_id)
        return PopulationSetStore(get_settings().postgres_url).freeze(
            segments,
            name=body.name,
            actor=principal.user_id,
            source_kind=source_kind,
            source_ref=source_ref,
            project_id=body.project_id,
            synthetic=True,
            acknowledged=body.acknowledged_synthetic,
        )
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get(
    "/{set_id}",
    response_model=PopulationSetResponse,
    responses={404: {"model": ApiError}},
)
def get_population(set_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        return PopulationSetStore(get_settings().postgres_url).get(set_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
