"""tests P5-M9: MCP server — ห่อ REST เดิมเท่านั้น (ADR-0005), auth ผ่าน env, error ส่งต่อชัด"""

import anyio
import httpx
import pytest

import api.mcp_server as mcp_mod


def _tool_names() -> set[str]:
    async def _list():
        return await mcp_mod.mcp.list_tools()

    return {t.name for t in anyio.run(_list)}


def test_all_tools_registered():
    names = _tool_names()
    assert names == {
        "run_dashboard",
        "compare_red_team",
        "resolve_prediction",
        "list_runs",
        "list_gallery",
        "get_insights",
    }


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_request_sends_api_key_and_base_url(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setenv("CHIMLANG_API_URL", "http://testhost:9000")
    monkeypatch.setenv("CHIMLANG_API_KEY", "secret-key")
    real_client = httpx.Client

    def fake_client(**kwargs):
        kwargs["transport"] = _mock_transport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(mcp_mod.httpx, "Client", fake_client)
    out = mcp_mod._request("GET", "/runs.json")
    assert out == {"ok": True}
    assert seen["url"].startswith("http://testhost:9000/") and seen["key"] == "secret-key"


def test_request_raises_with_api_detail(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "election เฉพาะ admin verified (GOV-02)"})

    real_client = httpx.Client
    monkeypatch.setattr(
        mcp_mod.httpx,
        "Client",
        lambda **kw: real_client(**{**kw, "transport": _mock_transport(handler)}),
    )
    with pytest.raises(RuntimeError, match="403.*GOV-02"):
        mcp_mod._request("GET", "/dashboard.json", params={"subject": "เลือกตั้ง"})


def test_resolve_tool_posts_outcome_body(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"prediction_id": 7, "outcome": "partial", "brier": 0.09})

    real_client = httpx.Client
    monkeypatch.setattr(
        mcp_mod.httpx,
        "Client",
        lambda **kw: real_client(**{**kw, "transport": _mock_transport(handler)}),
    )
    out = mcp_mod.resolve_prediction(7, "partial", "อ้างอิงข่าว")
    assert seen["method"] == "POST" and seen["path"] == "/predictions/7/resolve"
    assert "partial" in seen["body"] and out["brier"] == 0.09


def test_dashboard_tool_passes_params(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"subject": "x", "tipping_points": []})

    real_client = httpx.Client
    monkeypatch.setattr(
        mcp_mod.httpx,
        "Client",
        lambda **kw: real_client(**{**kw, "transport": _mock_transport(handler)}),
    )
    mcp_mod.run_dashboard("หัวข้อทดสอบ", agents=50)
    assert seen["params"] == {"subject": "หัวข้อทดสอบ", "agents": "50"}
