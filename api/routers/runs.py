from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from api.auth import get_principal, require
from api.models import validate_source_kinds
from core.run_quality import build_readiness
from governance.rbac import Permission, Principal

router = APIRouter(tags=["runs"])


class RunReadinessBody(BaseModel):
    engine: str = "fabric"
    subject: str
    domain: str = "general"
    agents: int = Field(100, ge=1)
    rounds: int = Field(3, ge=1, le=10)
    pack_id: int | None = None
    red_team: bool = False
    sources: list[dict] = []
    claim: str = ""
    measurement: str = ""
    due_days: int = 30
    views: list[str] = []
    live_news: bool = False
    parent_run_id: str = ""
    population_set_id: str = ""

    @field_validator("sources")
    @classmethod
    def _sources_kind_allowed(cls, v: list[dict]) -> list[dict]:
        return validate_source_kinds(v)


@router.post("/runs/readiness")
def run_readiness(body: RunReadinessBody, principal: Principal = Depends(get_principal)) -> dict:
    """Pre-run readiness and cost estimate. No LLM or external fetch is performed."""
    require(principal, Permission.RUN)
    return build_readiness(body.model_dump(), election_verified=principal.election_verified)
