"""Application, provider, secret, and budget settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_principal, require
from core.config import get_settings
from governance.rbac import Permission, Principal

router = APIRouter(prefix="/settings", tags=["settings"])


class SecretKeyBody(BaseModel):
    api_key: str


@router.get(".json")
def settings_json(principal: Principal = Depends(get_principal)) -> dict:
    from core.appsettings import get_app_settings

    settings = get_settings()
    try:
        data = get_app_settings(settings.postgres_url)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    from core.llm.budget import reserved_this_month, spent_this_month
    from core.llm.pricing import PricingRegistry
    from core.llm.userconfig import (
        LLM_PROVIDERS,
        effective_llm_settings,
        effective_monthly_cap,
    )
    from core.secretbox import mask, master_key_present

    effective = effective_llm_settings()
    key_from_db = bool(data.get("llm_api_key_enc"))
    active_key = effective.llm_api_key.strip()
    yaml_prices = {
        model: {
            "input_usd_per_m": price.input_usd_per_m,
            "output_usd_per_m": price.output_usd_per_m,
        }
        for model, price in PricingRegistry.from_yaml()._table.items()
    }
    try:
        spent = round(spent_this_month(settings.postgres_url), 4)
        reserved = round(reserved_this_month(settings.postgres_url), 4)
    except Exception:
        spent = 0.0
        reserved = 0.0
    from simulation.newsdesk import effective_news_config, effective_news_tuning

    effective_feeds, effective_tavily = effective_news_config(settings)
    effective_ttl, effective_max_age = effective_news_tuning(settings)
    news_config = {
        "feeds": effective_feeds,
        "cache_ttl_hours": effective_ttl,
        "max_age_days": effective_max_age,
        "feeds_source": "db"
        if str(data.get("news_rss_feeds", "")).strip()
        else ("env" if settings.news_rss_feeds_list() else "none"),
        "tavily_present": bool(effective_tavily),
        "tavily_masked": mask(effective_tavily) if effective_tavily else "",
        "tavily_source": "db"
        if data.get("tavily_api_key_enc")
        else ("env" if settings.tavily_api_key.strip() else "none"),
    }
    safe = {
        key: value
        for key, value in data.items()
        if key not in ("llm_api_key_enc", "tavily_api_key_enc")
    }
    return {
        **safe,
        "webhook_configured": bool(settings.alert_webhook_url.strip()),
        "auth_enabled": settings.auth_enabled,
        "caps": {
            "fabric": settings.max_agents_per_run,
            "debate": settings.max_agents_per_debate,
        },
        "llm": {
            "providers": [{"key": key, **value} for key, value in LLM_PROVIDERS.items()],
            "key_present": bool(active_key),
            "key_masked": mask(active_key) if active_key else "",
            "key_source": "db" if key_from_db else ("env" if active_key else "none"),
            "master_key_present": master_key_present(),
            "active_base_url": effective.llm_base_url,
            "active_model_crowd": effective.llm_model_crowd,
            "active_model_analyst": effective.llm_model_analyst,
            "synthesis_max_tokens": effective.llm_synthesis_max_tokens,
            "env_model_crowd": settings.llm_model_crowd,
            "env_model_analyst": settings.llm_model_analyst,
            "yaml_prices": yaml_prices,
        },
        "budget": {
            "run_cap_effective": effective.run_budget_usd_cap,
            "monthly_cap_effective": effective_monthly_cap(),
            "spent_this_month": spent,
            "reserved_this_month": reserved,
            "available_this_month": max(0.0, effective_monthly_cap() - spent - reserved),
            "env_run_cap": settings.run_budget_usd_cap,
            "env_monthly_cap": settings.monthly_budget_usd_cap,
        },
        "news": news_config,
    }


@router.put(".json")
def settings_put(patch: dict, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from core.appsettings import put_app_settings

    try:
        put_app_settings(get_settings().postgres_url, patch)
        return settings_json(principal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc


def _set_secret(kind: str, api_key: str) -> dict:
    from core.appsettings import set_llm_api_key, set_tavily_api_key
    from core.secretbox import MasterKeyMissingError

    setter = set_llm_api_key if kind == "llm" else set_tavily_api_key
    try:
        setter(get_settings().postgres_url, api_key)
    except MasterKeyMissingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {exc}") from exc
    return {"ok": True, "set": bool(api_key.strip())}


@router.put("/llm-key")
def settings_llm_key(body: SecretKeyBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.ADMIN)
    return _set_secret("llm", body.api_key)


@router.put("/tavily-key")
def settings_tavily_key(body: SecretKeyBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.ADMIN)
    return _set_secret("tavily", body.api_key)
