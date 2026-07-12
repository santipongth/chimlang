"""tests P5-M6: hub calculation (pure), graph summary endpoint, insights ข้าม run"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from graphlayer.summary import compute_hubs

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---- compute_hubs (pure — ไม่ต้องมี Neo4j) ----


def test_hubs_top_15_percent_capped_at_6():
    nodes = [{"name": f"n{i:02d}", "degree": 100 - i} for i in range(60)]
    hubs = compute_hubs(nodes)
    assert len(hubs) == 6  # 15% ของ 60 = 9 → cap 6
    assert hubs == [f"n{i:02d}" for i in range(6)]  # เรียงตาม degree


def test_hubs_small_graph_at_least_one():
    assert compute_hubs([{"name": "a", "degree": 3}, {"name": "b", "degree": 1}]) == ["a"]
    assert compute_hubs([]) == []


def test_hubs_zero_degree_graph_still_returns_one():
    # graph ที่ไม่มี edge เลย — ยังคืน node แรกเป็นตัวแทน (ไม่ crash)
    nodes = [{"name": "x", "degree": 0}, {"name": "y", "degree": 0}]
    assert compute_hubs(nodes) == ["x"]


def test_hubs_deterministic_tie_break_by_name():
    nodes = [{"name": "b", "degree": 5}, {"name": "a", "degree": 5}, {"name": "c", "degree": 1}]
    assert compute_hubs(nodes)[0] == "a"  # degree เท่ากัน → เรียงชื่อ (deterministic)


# ---- endpoints ----


def test_graph_summary_endpoint(client):
    r = client.get("/graph/summary.json")
    if r.status_code == 503:
        pytest.skip("Neo4j ไม่พร้อม (docker compose up -d)")
    data = r.json()
    assert set(data) >= {"nodes", "edges", "hubs", "kinds", "note"}
    # hub ต้องเป็น subset ของ nodes เสมอ
    names = {n["name"] for n in data["nodes"]}
    assert all(h in names for h in data["hubs"])


def test_insights_endpoint_shape(client):
    r = client.get("/insights.json")
    if r.status_code == 503:
        pytest.skip("PostgreSQL ไม่พร้อม (docker compose up -d)")
    data = r.json()
    assert set(data) >= {"total_runs", "exports", "runs_per_day", "predictions_by_domain"}
    assert isinstance(data["total_runs"], int)
    for d in data["predictions_by_domain"]:
        assert d["resolved"] <= d["total"]  # resolve เกินที่ลงทะเบียนไม่ได้
