from core.production_readiness import evaluate_production_readiness


def _secure_env() -> dict[str, str]:
    return {
        "AUTH_ENABLED": "true",
        "API_KEYS": f"{'k' * 32}:ops:admin",
        "PII_DETECTOR_ENABLED": "true",
        "WATERMARK_ENABLED": "true",
        "CHIMLANG_SECRET_KEY": "s" * 44,
        "POSTGRES_PASSWORD": "strong-postgres",
        "NEO4J_PASSWORD": "strong-neo4j",
    }


def test_self_hosted_readiness_never_exposes_secrets():
    env = _secure_env()
    report = evaluate_production_readiness(env)
    assert report["can_deploy"] is True
    assert report["secret_values_exposed"] is False
    assert "strong-postgres" not in str(report)


def test_public_ga_is_fail_closed_without_external_controls():
    report = evaluate_production_readiness(_secure_env(), profile="public-ga")
    assert report["can_deploy"] is False
    blocked = {item["id"] for item in report["checks"] if item["status"] == "block"}
    assert {"tls", "pen_test", "oidc", "tenant_isolation"} <= blocked


def test_public_ga_passes_when_all_declared_controls_exist():
    env = {
        **_secure_env(),
        "PUBLIC_BASE_URL": "https://chimlang.example",
        "PEN_TEST_REPORT_PATH": "audit.pdf",
        "OIDC_ISSUER_URL": "https://identity.example",
        "OIDC_CLIENT_ID": "chimlang",
        "TENANT_ISOLATION_MODE": "postgres_rls",
    }
    report = evaluate_production_readiness(
        env,
        profile="public-ga",
        path_exists=lambda path: path == "audit.pdf",
    )
    assert report["can_deploy"] is True
