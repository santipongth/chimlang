"""Fail-closed deployment readiness checks without exposing secret values."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessItem:
    id: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status, "detail": self.detail}


def _enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _api_keys_valid(raw: str) -> bool:
    entries = [entry.strip() for entry in raw.split(",") if entry.strip()]
    if not entries:
        return False
    roles = {"viewer", "analyst", "operator", "admin"}
    for entry in entries:
        parts = entry.split(":")
        if len(parts) < 3 or len(parts[0]) < 32 or parts[2] not in roles:
            return False
    return True


def evaluate_production_readiness(
    env: Mapping[str, str],
    *,
    profile: str = "self-hosted",
    path_exists: Callable[[str], bool] | None = None,
) -> dict:
    """Evaluate configuration only; returned details never contain secret values."""

    if profile not in {"self-hosted", "public-ga"}:
        raise ValueError("profile ต้องเป็น self-hosted หรือ public-ga")
    exists = path_exists or (lambda _path: False)
    checks: list[ReadinessItem] = []

    def add(check_id: str, ok: bool, pass_detail: str, block_detail: str) -> None:
        checks.append(
            ReadinessItem(check_id, "pass" if ok else "block", pass_detail if ok else block_detail)
        )

    add(
        "auth",
        _enabled(env.get("AUTH_ENABLED", "")),
        "API authentication enabled",
        "AUTH_ENABLED ต้องเป็น true",
    )
    add(
        "api_keys",
        _api_keys_valid(env.get("API_KEYS", "")),
        "API key format and minimum length valid",
        "API_KEYS ต้องมี key สุ่มยาวอย่างน้อย 32 ตัวและ role ที่รองรับ",
    )
    add(
        "pii",
        _enabled(env.get("PII_DETECTOR_ENABLED", "true")),
        "PII detector fail-closed",
        "PII detector ถูกปิด",
    )
    add(
        "watermark",
        _enabled(env.get("WATERMARK_ENABLED", "true")),
        "Export watermark enabled",
        "WATERMARK_ENABLED ต้องเป็น true",
    )
    add(
        "master_key",
        len(env.get("CHIMLANG_SECRET_KEY", "").strip()) >= 32,
        "Secret encryption key present",
        "CHIMLANG_SECRET_KEY ยังไม่พร้อม",
    )
    add(
        "postgres_password",
        env.get("POSTGRES_PASSWORD", "") not in {"", "chimlang"},
        "PostgreSQL password is not the development default",
        "POSTGRES_PASSWORD ยังเป็นค่าว่างหรือค่า dev",
    )
    add(
        "neo4j_password",
        env.get("NEO4J_PASSWORD", "") not in {"", "chimlang_dev"},
        "Neo4j password is not the development default",
        "NEO4J_PASSWORD ยังเป็นค่าว่างหรือค่า dev",
    )

    embedding_ready = bool(env.get("LLM_MODEL_EMBEDDING", "").strip())
    checks.append(
        ReadinessItem(
            "embedding",
            "pass" if embedding_ready else "warn",
            "Embedding model configured"
            if embedding_ready
            else "ยังใช้ BM25 fallback; ตั้ง model/ราคา/dimension ก่อนเปิด vector mode",
        )
    )

    if profile == "public-ga":
        public_url = env.get("PUBLIC_BASE_URL", "").strip().lower()
        add(
            "tls",
            public_url.startswith("https://"),
            "Public URL uses HTTPS",
            "PUBLIC_BASE_URL ต้องเป็น https:// และ terminate TLS ที่ reverse proxy",
        )
        report = env.get("PEN_TEST_REPORT_PATH", "").strip()
        add(
            "pen_test",
            bool(report) and exists(report),
            "Independent penetration-test report present",
            "ต้องมีรายงาน penetration test อิสระก่อน public GA",
        )
        issuer = env.get("OIDC_ISSUER_URL", "").strip().lower()
        add(
            "oidc",
            issuer.startswith("https://") and bool(env.get("OIDC_CLIENT_ID", "").strip()),
            "OIDC issuer/client configured",
            "ต้องเลือก OIDC provider และตั้ง issuer/client",
        )
        add(
            "tenant_isolation",
            env.get("TENANT_ISOLATION_MODE", "") == "postgres_rls",
            "PostgreSQL RLS tenant isolation selected",
            "multi-tenant ยังไม่มี PostgreSQL RLS policy",
        )
    else:
        checks.append(
            ReadinessItem(
                "public_ga_controls",
                "warn",
                "OIDC, tenant RLS, TLS, and independent pen test are required "
                "only before public GA",
            )
        )

    return {
        "profile": profile,
        "can_deploy": not any(item.status == "block" for item in checks),
        "checks": [item.to_dict() for item in checks],
        "secret_values_exposed": False,
    }
