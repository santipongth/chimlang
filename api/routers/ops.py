"""Operational health, Prometheus, and provider telemetry endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.auth import get_principal
from core.config import get_settings
from governance.rbac import Principal

router = APIRouter(tags=["operations"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "chimlang-api"}


@router.get("/health/deep")
def health_deep() -> dict:
    """Dependency status for monitoring; failures expose only safe exception types."""

    settings = get_settings()
    components: dict[str, str] = {}
    try:
        import psycopg

        with psycopg.connect(settings.postgres_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        components["postgres"] = "ok"
    except Exception as exc:
        components["postgres"] = f"down: {type(exc).__name__}"
    try:
        from core.tasks import celery_app

        with celery_app.connection() as conn:
            conn.ensure_connection(max_retries=1, timeout=3)
        components["redis"] = "ok"
    except Exception as exc:
        components["redis"] = f"down: {type(exc).__name__}"
    try:
        from graphlayer.store import Neo4jStore

        Neo4jStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password).verify()
        components["neo4j"] = "ok"
    except Exception as exc:
        components["neo4j"] = f"down: {type(exc).__name__}"
    overall = "ok" if all(value == "ok" for value in components.values()) else "degraded"
    return {"status": overall, "components": components}


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    from core.observability import prometheus_payload

    payload, content_type = prometheus_payload()
    return Response(content=payload, media_type=content_type)


@router.get("/observability.json")
def observability_json(
    hours: int = Query(24, ge=1, le=720), principal: Principal = Depends(get_principal)
) -> dict:
    from core.observability import provider_health

    try:
        return provider_health(get_settings().postgres_url, hours=hours)
    except Exception as exc:
        detail = f"อ่าน telemetry ไม่สำเร็จ: {type(exc).__name__}"
        raise HTTPException(status_code=503, detail=detail) from exc
