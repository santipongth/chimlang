"""Shared API request contracts used by routers, services, and Celery tasks."""

from typing import Literal

from pydantic import BaseModel, Field


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
    retrieval_mode: Literal["hybrid", "bm25", "vector"] = "hybrid"
    parent_run_id: str = ""
    reflection: bool = False
    experiment_id: str = ""
