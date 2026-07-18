"""Shared API request contracts used by routers, services, and Celery tasks."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def validate_source_kinds(sources: list[dict]) -> list[dict]:
    """ADR-0027: evidence source รับเฉพาะ kind text/url — kind อื่น (รวม rss เดิม) = 422"""
    from simulation.sources import ALLOWED_SOURCE_KINDS

    for source in sources:
        kind = str(source.get("kind", "text"))
        if kind not in ALLOWED_SOURCE_KINDS:
            raise ValueError(f"source kind '{kind}' ไม่รองรับ — ใช้ได้เฉพาะ text หรือ url (ADR-0027)")
    return sources


class RunBody(BaseModel):
    engine: Literal["fabric", "debate"] = "fabric"
    subject: str
    domain: str = "ทั่วไป"
    agents: int = Field(100, ge=1)
    rounds: int = Field(3, ge=1, le=10)
    pack_id: int | None = None
    red_team: bool = False
    sources: list[dict] = Field(default_factory=list)
    claim: str = ""
    measurement: str = ""
    due_days: int = 30
    probability: float | None = Field(None, ge=0.01, le=0.99)
    seed: int | None = None
    views: list[str] = Field(default_factory=list)
    live_news: bool = False
    parent_run_id: str = ""
    experiment_id: str = ""
    population_set_id: str = ""
    input_mode: Literal["latest", "frozen"] = "latest"
    source_run_id: str = ""

    @field_validator("sources")
    @classmethod
    def _sources_kind_allowed(cls, v: list[dict]) -> list[dict]:
        return validate_source_kinds(v)


class ApiError(BaseModel):
    detail: str


class AsyncRunAccepted(BaseModel):
    run_id: str
    job_id: str = ""
    status: str
    reused: bool = False
    status_url: str
    events_url: str
    manifest_url: str
    snapshot_url: str
    result: dict[str, Any] | None = None


class CancelRunResponse(BaseModel):
    ok: bool
    status: str
    transitioned: bool


class RerunBody(BaseModel):
    input_mode: Literal["frozen", "latest"]


class RunSpecResponse(BaseModel):
    schema_version: int
    request: dict[str, Any]
    seed: int
    population_snapshot: dict[str, Any]
    input_mode: Literal["latest", "frozen"]
    source_run_id: str


class ManifestResponse(BaseModel):
    run_id: str
    schema_version: int
    status: str = "legacy"
    complete: bool
    reproducibility: str
    incomplete_reasons: list[str] = Field(default_factory=list)
    determinism: str = "provider-best-effort"
    spec: RunSpecResponse | dict[str, Any] = Field(default_factory=dict)
    versions: dict[str, Any] = Field(default_factory=dict)
    pricing: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)
    snapshots: dict[str, Any] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    config_hash: str = ""
    manifest_hash: str = ""
    created_at: str | None = None
    reason: str = ""


class SnapshotResponse(BaseModel):
    run_id: str
    manifest_hash: str
    config_hash: str
    status: str
    engine: str
    subject: str
    payload: dict[str, Any]
