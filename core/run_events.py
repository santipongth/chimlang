"""Safe run-event envelope and best-effort Redis wake-up notifications."""

import re
from threading import Lock

_ALLOWED_PAYLOAD_KEYS = {
    "engine",
    "status",
    "parent_run_id",
    "job_id",
    "progress",
    "cost_usd",
    "reason",
    "attempt",
    "run_id",
}
_SECRET_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|secret|bearer|sk-[a-z0-9_-]{8,}|token\s*[=:])"
)
_REDIS_CLIENT = None
_REDIS_LOCK = Lock()


def safe_event_message(message: str) -> str:
    """Return a short message that passed secret and PII policy."""
    value = re.sub(r"\s+", " ", str(message or "")).strip()[:500]
    if not value:
        return ""
    if _SECRET_PATTERN.search(value):
        return "รายละเอียดถูกซ่อนตามนโยบาย secrets"
    try:
        from core.config import get_settings
        from governance.pii import PIIDetector, load_allowlist

        if not get_settings().pii_detector_enabled:
            return "รายละเอียดถูกซ่อนเพราะ PII detector ไม่พร้อม"
        if PIIDetector(load_allowlist()).check(value).blocked:
            return "รายละเอียดถูกซ่อนตามนโยบาย PII"
    except Exception:
        return "รายละเอียดถูกซ่อนเพราะตรวจ PII ไม่สำเร็จ"
    return value


def safe_event_payload(payload: dict) -> dict:
    """Whitelist operational metadata; prompts, content, and credentials never enter events."""
    safe: dict = {}
    for key, value in payload.items():
        if key not in _ALLOWED_PAYLOAD_KEYS:
            continue
        if isinstance(value, str):
            safe[key] = safe_event_message(value)
        elif value is None or isinstance(value, (bool, int, float)):
            safe[key] = value
    return safe


def _redis_client():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    with _REDIS_LOCK:
        if _REDIS_CLIENT is None:
            import redis

            from core.config import get_settings

            _REDIS_CLIENT = redis.Redis.from_url(
                get_settings().redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
    return _REDIS_CLIENT


def publish_event(run_id: str, event_id: int) -> None:
    """Wake live SSE subscribers; durable replay always comes from PostgreSQL."""
    try:
        _redis_client().publish(f"chimlang:run-events:{run_id}", str(event_id))
    except Exception:
        # Redis notification is an optimization. PostgreSQL replay remains authoritative.
        return
