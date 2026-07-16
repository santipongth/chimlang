"""tests P1-M6: Executive Brief AC (≤3 บรรทัด + fragility), heatmap, HTML, REST + election block"""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.dashboard import (
    Dashboard,
    ScenarioColumn,
    build_executive_brief,
    build_risk_heatmap,
)
from api.render import render_dashboard_html
from simulation.experiment import DeltaEstimate
from simulation.redteam import Attack, ScoredAttack
from trust.universe import FragilityReport, UniverseResult


def _fragility(index: int) -> FragilityReport:
    est = DeltaEstimate("m", (-0.18,), -0.18, (-0.26, -0.10))
    return FragilityReport(
        universes=(UniverseResult(0, None, est, "ลดลง"),),
        majority_conclusion="ลดลง",
        fragility_index=index,
    )


def _scored(role: str, lk: int, dm: int) -> ScoredAttack:
    return ScoredAttack(Attack("r", role, "โจมตี", "จุดอ่อน", "ช่องทาง"), lk, dm, "เหตุผล")


def test_brief_max_three_lines_with_fragility_and_range():
    brief = build_executive_brief(
        delta_ci=(-0.26, -0.10),
        fragility=_fragility(0),
        top_risk=_scored("IO", 5, 5),
        subject="ทดสอบ",
    )
    assert len(brief.lines) <= 3  # AC ของ DASH-01
    assert brief.fragility_index == 0
    assert brief.headline_range == (-0.26, -0.10)  # ช่วงเสมอ ไม่ใช่ตัวเลขเดี่ยว
    # ต้องมีทั้งบรรทัดโอกาสและความเสี่ยง
    kinds = {ln.kind for ln in brief.lines}
    assert "opportunity" in kinds and "risk" in kinds


def test_brief_rejects_more_than_three_lines():
    from api.dashboard import BriefLine, ExecutiveBrief

    with pytest.raises(ValueError):
        ExecutiveBrief(
            lines=tuple(BriefLine("risk", f"x{i}") for i in range(4)),
            fragility_index=0,
            confidence_label="l",
            headline_range=(0.0, 0.1),
        )


def test_heatmap_bands_and_max_per_role():
    cells = build_risk_heatmap([_scored("IO", 5, 5), _scored("IO", 2, 2), _scored("troll", 2, 1)])
    io = next(c for c in cells if c.segment_or_role == "IO")
    assert io.risk == 25 and io.band == "สูง"  # เอา max ต่อบทบาท
    troll = next(c for c in cells if c.segment_or_role == "troll")
    assert troll.band == "ต่ำ"
    assert [c.risk for c in cells] == sorted([c.risk for c in cells], reverse=True)


def test_dashboard_to_dict_and_html():
    dash = Dashboard(
        subject="มาตรการทดสอบ",
        brief=build_executive_brief(
            delta_ci=(-0.26, -0.10),
            fragility=_fragility(20),
            top_risk=_scored("IO", 4, 5),
            subject="มาตรการทดสอบ",
        ),
        heatmap=tuple(build_risk_heatmap([_scored("IO", 4, 5)])),
        scenarios=(
            ScenarioColumn("baseline", {"กลุ่มA": 0.8, "กลุ่มB": 0.5}),
            ScenarioColumn("variant", {"กลุ่มA": 0.3, "กลุ่มB": 0.2}),
        ),
        voices=({"private": "ไม่เชื่อหรอก", "public": "", "segment": "กลุ่มA"},),
        universe_estimates=(
            {"universe_id": 0, "estimate": -0.18, "ci95": [-0.26, -0.10], "conclusion": "ลดลง"},
        ),
    )
    d = dash.to_dict()
    assert d["brief"]["fragility_index"] == 20
    assert len(d["brief"]["headline_range"]) == 2
    assert d["universe_estimates"][0]["estimate"] == -0.18
    html = render_dashboard_html(dash)
    assert "not a real poll" in html  # watermark banner
    assert "Executive Brief" in html and "Risk Heatmap" in html
    assert "กลุ่มA" in html


# --- REST API ---


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_dashboard_json_non_election(client):
    r = client.get("/dashboard.json", params={"subject": "มาตรการค่าธรรมเนียมรถติด กทม."})
    assert r.status_code == 200
    body = r.json()
    assert body["brief"]["lines"] and len(body["brief"]["lines"]) <= 3
    assert "fragility_index" in body["brief"]
    assert len(body["scenarios"]) == 2  # baseline vs variant


def test_election_scenario_blocks_individual_granularity(client):
    # GOV-02: subject การเมือง + ขอ individual → 403
    r = client.get(
        "/dashboard.json",
        params={"subject": "จำลองผลเลือกตั้งผู้ว่าฯ", "granularity": "individual"},
    )
    assert r.status_code == 403
    assert "election mode" in r.json()["detail"]


def test_election_scenario_aggregate_allowed(client):
    r = client.get(
        "/dashboard.json",
        params={"subject": "จำลองปฏิกิริยาต่อผู้สมัครเลือกตั้ง", "granularity": "aggregate"},
    )
    assert r.status_code == 200  # aggregate ผ่านได้แม้เป็น election scenario


def test_dashboard_html_renders(client):
    r = client.get("/dashboard.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<h1>" in r.text


def test_dashboard_agents_param_capped(client):
    # P4-M1: ผู้เรียกขอ agents ได้ แต่ไม่เกิน cap ต่อ run — ค่าเล็กเพื่อความเร็ว
    r = client.get("/dashboard.json", params={"agents": 20})
    assert r.status_code == 200
    r_bad = client.get("/dashboard.json", params={"agents": 3})
    assert r_bad.status_code == 422  # ต่ำกว่า ge=10


def test_runs_endpoint_lists_recent_runs(client):
    import psycopg

    try:
        r = client.get("/runs.json")
    except psycopg.OperationalError:
        import pytest as _pytest

        _pytest.skip("PostgreSQL ไม่พร้อม")
    if r.status_code == 503:
        import pytest as _pytest

        _pytest.skip("PostgreSQL ไม่พร้อม")
    body = r.json()
    assert "runs" in body and "due" in body
    if body["runs"]:
        first = body["runs"][0]
        assert {"run_id", "started", "predictions", "exported"} <= set(first)


def test_web_dist_served_when_built(client):
    from api.app import _WEB_DIST

    if not _WEB_DIST.exists():
        import pytest as _pytest

        _pytest.skip("web/dist ยังไม่ build (npm run build)")
    r = client.get("/app/")
    assert r.status_code == 200
    assert "ชิมลาง" in r.text  # title จาก index.html
