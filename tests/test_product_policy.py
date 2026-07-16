from fastapi.testclient import TestClient

from api.app import app
from core.product_policy import active_product_policy


def test_active_policy_keeps_unapproved_business_features_disabled():
    policy = active_product_policy()
    assert policy["billing_enabled"] is False
    assert policy["repository_public"] is False
    assert policy["semantic_memory_enabled"] is False
    by_key = {item["key"]: item for item in policy["items"]}
    assert by_key["election_eligibility"]["active_default"] == (
        "verified_admin_only_aggregate_output"
    )
    assert "30 paired runs" in by_key["semantic_memory"]["change_gate"]


def test_product_policy_endpoint_is_read_only_and_authenticated():
    response = TestClient(app).get("/product-policy.json")
    assert response.status_code == 200
    assert response.json()["billing_enabled"] is False
