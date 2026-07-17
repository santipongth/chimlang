"""tests P4-M6: security headers, /health/deep, PDF สองภาษา (NFR-05/06/09)"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from api.app import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_security_headers_on_every_response(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "same-origin"


def test_health_deep_reports_components(client):
    r = client.get("/health/deep")
    assert r.status_code == 200
    body = r.json()
    assert set(body["components"]) == {"postgres", "redis", "worker", "neo4j"}
    assert body["status"] in ("ok", "degraded")
    if all(v == "ok" for v in body["components"].values()):
        assert body["status"] == "ok"  # ทุกตัว ok = overall ok


def test_pdf_english_labels(client):
    r = client.get("/dashboard.pdf", params={"agents": 20, "lang": "en"})
    assert r.status_code == 200
    text = "".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    assert "Key findings" in text and "Headline range" in text  # NFR-09

    bad = client.get("/dashboard.pdf", params={"agents": 20, "lang": "jp"})
    assert bad.status_code == 422  # จำกัด th|en เท่านั้น
