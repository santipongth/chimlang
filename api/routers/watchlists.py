"""Watchlist and alert endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_principal, require, require_election
from core.config import get_settings
from governance.election import ElectionPolicy, classify_scenario
from governance.rbac import Permission, Principal

router = APIRouter(tags=["watchlists"])


class WatchlistBody(BaseModel):
    label: str
    subject: str
    agents: int = Field(100, ge=1)
    cadence: str = "daily"


class AlertReadBody(BaseModel):
    id: int | None = None
    all: bool = False


@router.get("/watchlists.json")
def watchlists_json(principal: Principal = Depends(get_principal)) -> dict:
    from governance.watchlist import WatchlistStore

    settings = get_settings()
    try:
        store = WatchlistStore(settings.postgres_url)
        items = [item.__dict__ for item in store.list_watchlists()]
        alerts = store.list_alerts(limit=50)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {
        "items": items,
        "alerts": alerts,
        "unread": sum(1 for alert in alerts if not alert["read"]),
        "webhook_configured": bool(settings.alert_webhook_url.strip()),
    }


@router.post("/watchlists")
def watchlist_create(body: WatchlistBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    if ElectionPolicy(classify_scenario(body.subject)).active:
        require_election(principal)
    from governance.watchlist import WatchlistStore

    settings = get_settings()
    try:
        watchlist_id = WatchlistStore(settings.postgres_url).create(
            label=body.label.strip() or body.subject[:40],
            subject=body.subject.strip(),
            agents=min(body.agents, settings.max_agents_per_run),
            cadence=body.cadence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"id": watchlist_id}


@router.delete("/watchlists/{watchlist_id}")
def watchlist_delete(watchlist_id: int, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from governance.watchlist import WatchlistStore

    try:
        WatchlistStore(get_settings().postgres_url).delete(watchlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"ok": True}


@router.post("/watchlists/{watchlist_id}/toggle")
def watchlist_toggle(
    watchlist_id: int,
    active: bool = Query(...),
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    from governance.watchlist import WatchlistStore

    try:
        WatchlistStore(get_settings().postgres_url).set_active(watchlist_id, active)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"id": watchlist_id, "active": active}


@router.post("/watchlists/{watchlist_id}/run")
def watchlist_run_now(watchlist_id: int, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from governance.watchlist import WatchlistStore, check_watchlist, default_runner

    try:
        store = WatchlistStore(get_settings().postgres_url)
        watchlist = store.get(watchlist_id)
        if ElectionPolicy(classify_scenario(watchlist.subject)).active:
            require_election(principal)
        created = check_watchlist(store, watchlist, runner=default_runner)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"id": watchlist_id, "alerts_created": created}


@router.post("/alerts/read")
def alerts_read(body: AlertReadBody, principal: Principal = Depends(get_principal)) -> dict:
    from governance.watchlist import WatchlistStore

    try:
        WatchlistStore(get_settings().postgres_url).mark_read(body.id, all_alerts=body.all)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"ok": True}
