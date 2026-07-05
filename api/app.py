"""FastAPI app (Presentation layer) — REST endpoint สำหรับ dashboard + health

Phase 1 ขอบเขต: endpoint อ่านผล what-if ที่รันแล้ว (กลไกล้วน ไม่เรียก LLM ใน request path
เพื่อไม่ให้ HTTP timeout และคุมต้นทุน) + คืน JSON/HTML ที่ประกอบ dashboard

ทุก scenario ถูกตรวจ election mode; response ระดับ individual ถูก block ถ้าเข้าโหมด (GOV-02)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from api.dashboard import (
    Dashboard,
    ScenarioColumn,
    build_executive_brief,
    build_risk_heatmap,
)
from api.render import render_dashboard_html
from core.config import get_settings
from governance.election import ElectionModeError, ElectionPolicy, classify_scenario
from simulation.engine import Message
from simulation.persona import PersonaFactory
from simulation.provenance import build_cards
from trust.universe import run_multiverse_whatif

app = FastAPI(title="ชิมลาง API", version="0.1.0")

RUMOR = "ข่าวลือ: จะเก็บค่าธรรมเนียมมอเตอร์ไซค์ด้วยคันละ 50 บาทต่อวัน"
EVENT = "กทม. แถลงชี้แจงทางการ: ร่างมาตรการยกเว้นมอเตอร์ไซค์ทุกประเภท"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "chimlang-api"}


def _run_dashboard(subject: str, granularity: str) -> Dashboard:
    settings = get_settings()
    policy = ElectionPolicy(classify_scenario(subject))
    policy.require_aggregate(granularity)  # GOV-02: individual ถูก block ใน election mode

    n = settings.max_agents_dev
    factory = PersonaFactory()
    fragility, outcomes = run_multiverse_whatif(
        factory,
        n_agents=n,
        max_agents=n,
        universes=5,
        seeds_per_universe=4,
        rounds=20,
        base_messages=[Message("rumor", "rumor", RUMOR, 1, "public_feed")],
        event=Message("official", "correction", EVENT, 8, "public_feed", counters="rumor"),
        target_msg_id="rumor",
        base_seed=settings.default_seed,
    )
    base = outcomes[0]

    def belief_by_seg(result) -> dict[str, float]:
        from collections import defaultdict

        agg: dict[str, list[bool]] = defaultdict(list)
        for st in result.states.values():
            agg[st.persona.segment_name].append(bool(st.believed.get("rumor")))
        return {seg: sum(v) / len(v) for seg, v in agg.items()}

    brief = build_executive_brief(
        delta_ci=fragility.universes[0].estimate.ci95,
        fragility=fragility,
        top_risk=None,
        subject=subject,
    )
    cards = build_cards()
    dash = Dashboard(
        subject=subject,
        brief=brief,
        heatmap=tuple(build_risk_heatmap([])),
        scenarios=(
            ScenarioColumn("ไม่มีคำชี้แจง (baseline)", belief_by_seg(base.baseline)),
            ScenarioColumn("มีคำชี้แจง (variant)", belief_by_seg(base.variant)),
        ),
        voice_population_share=tuple(
            {"segment": c.segment_name, "population_share": c.share} for c in cards
        ),
    )
    return dash


@app.get("/dashboard.json")
def dashboard_json(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    granularity: str = Query("aggregate"),
) -> dict:
    try:
        dash = _run_dashboard(subject, granularity)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return dash.to_dict()


@app.get("/dashboard.html", response_class=HTMLResponse)
def dashboard_html(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    granularity: str = Query("aggregate"),
) -> str:
    try:
        dash = _run_dashboard(subject, granularity)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return render_dashboard_html(dash)
