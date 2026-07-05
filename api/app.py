"""FastAPI app (Presentation layer) — REST endpoint สำหรับ dashboard + health

Phase 1 ขอบเขต: endpoint อ่านผล what-if ที่รันแล้ว (กลไกล้วน ไม่เรียก LLM ใน request path
เพื่อไม่ให้ HTTP timeout และคุมต้นทุน) + คืน JSON/HTML ที่ประกอบ dashboard

ทุก scenario ถูกตรวจ election mode; response ระดับ individual ถูก block ถ้าเข้าโหมด (GOV-02)
"""

import time
from collections import deque
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

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
from simulation.persona import DEFAULT_SEGMENTS_PATH, PersonaFactory
from simulation.provenance import build_cards
from trust.signal import build_signal_bundle
from trust.signal_harness import SampleTooSmallError, evaluate
from trust.universe import run_multiverse_whatif

app = FastAPI(title="ชิมลาง API", version="0.1.0")


class RateLimiter:
    """SIG-04: จำกัดอัตราเรียก signal endpoint — เกิน = 429"""

    def __init__(self, max_calls: int, window_s: float):
        self.max_calls = max_calls
        self.window_s = window_s
        self._calls: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.window_s:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            return False
        self._calls.append(now)
        return True


signal_rate_limiter = RateLimiter(max_calls=30, window_s=60.0)

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


@app.get("/signal.json")
def signal_json(subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม.")) -> dict:
    """SIG-01/03/04 — features พร้อมช่วง + metadata บังคับ; election = ปิด (GOV-02)"""
    if not signal_rate_limiter.allow():
        raise HTTPException(status_code=429, detail="rate limit: signal endpoint (SIG-04)")
    policy = ElectionPolicy(classify_scenario(subject))
    try:
        policy.guard_sim_to_signal()  # GOV-02: scenario เลือกตั้ง/การเมือง = signal ปิดตาย
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    settings = get_settings()
    n = settings.max_agents_dev
    fragility, outcomes = run_multiverse_whatif(
        PersonaFactory(),
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
    bundle = build_signal_bundle(
        [o.baseline for o in outcomes],
        "rumor",
        rounds=20,
        fragility=fragility,
        run_id=f"signal-{datetime.now():%Y%m%d-%H%M%S}",
        calibration_note=(
            "ยังไม่มี prediction ที่ resolve ในโดเมนนี้ — ดู docs/reports/public-benchmark.md"
        ),
        model_version="mechanistic-engine@dev",
        provenance_source=DEFAULT_SEGMENTS_PATH,
    )
    return bundle.to_dict()


class OOSRequest(BaseModel):
    feature_series: list[float]  # ค่า feature เรียงตามเวลา
    target_series: list[float]  # ผลจริง (เช่น การเปลี่ยนแปลงยอด/ราคา) เรียงตามเวลาเดียวกัน


@app.post("/signal/oos-test.json")
def signal_oos_test(req: OOSRequest) -> dict:
    """SIG-02 — ทดสอบ out-of-sample ว่า feature เพิ่ม predictive power จริงไหม"""
    try:
        report = evaluate(req.feature_series, req.target_series)
    except SampleTooSmallError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return report.to_dict()
