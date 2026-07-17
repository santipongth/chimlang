"""Turn-by-turn rehearsal API with persistent checkpoints and BudgetGuard."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_principal, require
from api.models import ApiError
from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, TierLoad
from core.llm.budget import (
    check_monthly_budget,
    release_budget_reservation,
    reserve_monthly_budget,
)
from core.llm.userconfig import effective_llm_settings, effective_monthly_cap, effective_pricing
from core.rehearsal_store import RehearsalStore
from governance.pii import PIIDetector, load_allowlist
from governance.rbac import Permission, Principal
from simulation.persona import PersonaFactory
from simulation.rehearsal import JOURNALISTS, RehearsalSession, Turn

router = APIRouter(prefix="/rehearsals", tags=["rehearsals"])


class RehearsalCreateBody(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    scenario: str = Field(min_length=4, max_length=20_000)
    seed: int | None = None
    netizens: int = Field(default=4, ge=1, le=20)
    max_turns: int = Field(default=8, ge=1, le=20)
    reactions_per_turn: int = Field(default=2, ge=0, le=5)


class RehearsalAnswerBody(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class RehearsalDecisionBody(BaseModel):
    decision: str = Field(min_length=1, max_length=10_000)


class RehearsalControlBody(BaseModel):
    action: Literal["pause", "resume"]


class RehearsalSummaryResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    title: str
    status: str
    cost_usd: float


class RehearsalListResponse(BaseModel):
    rehearsals: list[RehearsalSummaryResponse]


class RehearsalResponse(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    title: str
    scenario: str
    status: str
    seed: int
    netizens: int
    max_turns: int
    reactions_per_turn: int
    cost_usd: float
    created_by: str
    turns: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    scorecard: dict[str, Any] | None
    events: list[dict[str, Any]]


def _store() -> RehearsalStore:
    return RehearsalStore(get_settings().postgres_url)


def _pii_check(value: str) -> None:
    settings = get_settings()
    if not settings.pii_detector_enabled:
        raise HTTPException(status_code=503, detail="PII detector ถูกปิด")
    if PIIDetector(load_allowlist()).check(value).blocked:
        raise HTTPException(status_code=422, detail="พบ PII — rehearsal input/output ถูกปฏิเสธ")


def _loads(*, crowd_calls: int = 0, analyst_calls: int = 0) -> list[TierLoad]:
    settings = effective_llm_settings()
    loads = []
    if crowd_calls:
        loads.append(TierLoad(settings.llm_model_crowd, crowd_calls, 3500, 250))
    if analyst_calls:
        loads.append(TierLoad(settings.llm_model_analyst, analyst_calls, 4000, 800))
    return loads


def _preflight(
    loads: list[TierLoad],
    *,
    remaining_cap: float | None = None,
    reservation_id: str = "",
    reserve: bool = False,
) -> tuple[LLMAdapter, BudgetGuard]:
    settings = effective_llm_settings()
    pricing = effective_pricing()
    estimate = CostEstimator(pricing).estimate(loads)
    monthly_cap = effective_monthly_cap()
    if reserve and reservation_id:
        reserve_monthly_budget(
            settings.postgres_url,
            {reservation_id: estimate.total_usd},
            monthly_cap,
            context="rehearsal_session",
        )
    else:
        check_monthly_budget(
            settings.postgres_url,
            estimate.total_usd,
            monthly_cap,
            reservation_id=reservation_id,
        )
    cap = settings.run_budget_usd_cap if remaining_cap is None else remaining_cap
    if cap <= 0:
        raise ValueError("rehearsal ใช้งบต่อ session ครบแล้ว")
    guard = BudgetGuard(cap_usd=cap)
    guard.check_estimate(estimate)
    return (
        LLMAdapter(
            settings,
            pricing,
            guard,
            run_id=reservation_id,
            monthly_cap_usd=monthly_cap,
            monthly_reservation_id=reservation_id,
        ),
        guard,
    )


def _session(adapter: LLMAdapter, detail: dict) -> RehearsalSession:
    netizens = PersonaFactory().sample(
        detail["netizens"],
        seed=detail["seed"],
        max_agents=get_settings().max_agents_per_run,
    )
    session = RehearsalSession(
        adapter,
        detail["scenario"],
        netizens,
        seed=detail["seed"],
        max_agents=get_settings().max_agents_per_run,
        reactions_per_turn=detail["reactions_per_turn"],
    )
    session.turns = [
        Turn(
            turn_no=turn["turn_no"],
            journalist=turn["journalist"],
            question=turn["question"],
            answer=turn["answer"],
            reactions=tuple(turn["reactions"]),
            question_latency_s=float(turn["question_latency_s"]),
        )
        for turn in detail["turns"]
        if turn["answered"]
    ]
    return session


def _remaining(detail: dict) -> float:
    return max(0.0, effective_llm_settings().run_budget_usd_cap - detail["cost_usd"])


@router.get("", response_model=RehearsalListResponse)
def list_rehearsals(
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
) -> dict:
    return {"rehearsals": _store().list(limit=limit)}


@router.post(
    "",
    status_code=201,
    response_model=RehearsalResponse,
    responses={422: {"model": ApiError}},
)
def create_rehearsal(
    body: RehearsalCreateBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    _pii_check(body.title + "\n" + body.scenario)
    if len(JOURNALISTS) + body.netizens > get_settings().max_agents_per_run:
        raise HTTPException(status_code=422, detail="ผู้เข้าร่วมเกิน agent cap")
    store = _store()
    session_id = store.new_session_id()
    try:
        # Aggregate preflight for the whole session before any provider call.
        _preflight(
            _loads(
                crowd_calls=body.max_turns * (1 + body.reactions_per_turn),
                analyst_calls=2,
            ),
            reservation_id=session_id,
            reserve=True,
        )
        return store.create(
            title=body.title,
            scenario=body.scenario,
            seed=body.seed if body.seed is not None else get_settings().default_seed,
            netizens=body.netizens,
            max_turns=body.max_turns,
            reactions_per_turn=body.reactions_per_turn,
            actor=principal.user_id,
            session_id=session_id,
        )
    except (ValueError, RuntimeError) as exc:
        release_budget_reservation(get_settings().postgres_url, session_id)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{session_id}",
    response_model=RehearsalResponse,
    responses={404: {"model": ApiError}},
)
def get_rehearsal(session_id: str, principal: Principal = Depends(get_principal)) -> dict:
    try:
        return _store().get(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{session_id}/next",
    response_model=RehearsalResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
)
def next_question(session_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    store = _store()
    lease = ""
    try:
        lease = store.acquire_operation(session_id, "next_question")
        detail = store.get(session_id)
        if detail["status"] != "active":
            raise ValueError("rehearsal ต้อง active ก่อนถามคำถามถัดไป")
        if detail["turns"] and not detail["turns"][-1]["answered"]:
            raise ValueError("ต้องตอบคำถามปัจจุบันก่อน")
        if len(detail["turns"]) >= detail["max_turns"]:
            raise ValueError("ครบจำนวนคำถามสูงสุดแล้ว")
        adapter, guard = _preflight(
            _loads(crowd_calls=1),
            remaining_cap=_remaining(detail),
            reservation_id=session_id,
        )
        try:
            role, question, latency = _session(adapter, detail).next_question()
            _pii_check(question)
        finally:
            store.add_cost(session_id, guard.spent_usd)
        return store.append_event(
            session_id,
            event_type="question",
            turn_no=len(detail["turns"]) + 1,
            actor=principal.user_id,
            payload={
                "journalist_id": role.role_id,
                "journalist": role.name,
                "question": question,
                "latency_s": round(latency, 3),
            },
            require_status="active",
        )
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        store.release_operation(session_id, lease)


@router.post(
    "/{session_id}/answer",
    response_model=RehearsalResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
)
def answer_question(
    session_id: str,
    body: RehearsalAnswerBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    _pii_check(body.answer)
    store = _store()
    lease = ""
    try:
        lease = store.acquire_operation(session_id, "answer_question")
        detail = store.get(session_id)
        if detail["status"] != "active" or not detail["turns"]:
            raise ValueError("ไม่มีคำถาม active ให้ตอบ")
        pending = detail["turns"][-1]
        if pending["answered"]:
            raise ValueError("คำถามนี้ถูกตอบแล้ว")
        calls = detail["reactions_per_turn"]
        adapter, guard = _preflight(
            _loads(crowd_calls=calls),
            remaining_cap=_remaining(detail),
            reservation_id=session_id,
        )
        try:
            session = _session(adapter, detail)
            role = next(item for item in JOURNALISTS if item.role_id == pending["journalist_id"])
            turn = session.submit_answer(
                role,
                pending["question"],
                body.answer,
                pending["question_latency_s"],
            )
            _pii_check("\n".join(turn.reactions))
        finally:
            store.add_cost(session_id, guard.spent_usd)
        return store.append_event(
            session_id,
            event_type="answer",
            turn_no=pending["turn_no"],
            actor=principal.user_id,
            payload={"answer": body.answer, "reactions": list(turn.reactions)},
            require_status="active",
        )
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        store.release_operation(session_id, lease)


@router.post(
    "/{session_id}/control",
    response_model=RehearsalResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}},
)
def control_rehearsal(
    session_id: str,
    body: RehearsalControlBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    expected, target = ("active", "paused") if body.action == "pause" else ("paused", "active")
    try:
        return _store().transition(
            session_id, expected=expected, target=target, actor=principal.user_id
        )
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post(
    "/{session_id}/decisions",
    response_model=RehearsalResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
)
def log_decision(
    session_id: str,
    body: RehearsalDecisionBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    _pii_check(body.decision)
    try:
        return _store().append_event(
            session_id,
            event_type="decision",
            actor=principal.user_id,
            payload={"decision": body.decision},
        )
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post(
    "/{session_id}/finish",
    response_model=RehearsalResponse,
    responses={404: {"model": ApiError}, 409: {"model": ApiError}, 422: {"model": ApiError}},
)
def finish_rehearsal(session_id: str, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    store = _store()
    lease = ""
    try:
        lease = store.acquire_operation(session_id, "finish")
        detail = store.get(session_id)
        if detail["status"] != "active":
            raise ValueError("rehearsal ต้อง active ก่อนจบ")
        if not detail["turns"] or any(not turn["answered"] for turn in detail["turns"]):
            raise ValueError("ต้องมีคำตอบครบอย่างน้อยหนึ่ง turn ก่อนจบ")
        adapter, guard = _preflight(
            _loads(analyst_calls=2),
            remaining_cap=_remaining(detail),
            reservation_id=session_id,
        )
        try:
            card = _session(adapter, detail).scorecard()
            payload = {
                "calmed": list(card.calmed),
                "inflamed": list(card.inflamed),
                "risky_quotes": list(card.risky_quotes),
                "summary": card.summary,
                "parse_ok": card.parse_ok,
                "simulation_estimate": True,
                "gov05_no_ghostwriting": True,
            }
            _pii_check(json.dumps(payload, ensure_ascii=False))
        finally:
            store.add_cost(session_id, guard.spent_usd)
        finished = store.finish(session_id, scorecard=payload, actor=principal.user_id)
        release_budget_reservation(get_settings().postgres_url, session_id)
        return finished
    except ValueError as exc:
        status = 404 if str(exc).startswith("ไม่พบ") else 409
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        store.release_operation(session_id, lease)
