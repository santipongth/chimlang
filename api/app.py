"""FastAPI app (Presentation layer) — REST endpoint สำหรับ dashboard + health

Phase 1 ขอบเขต: endpoint อ่านผล what-if ที่รันแล้ว (กลไกล้วน ไม่เรียก LLM ใน request path
เพื่อไม่ให้ HTTP timeout และคุมต้นทุน) + คืน JSON/HTML ที่ประกอบ dashboard

ทุก scenario ถูกตรวจ election mode; response ระดับ individual ถูก block ถ้าเข้าโหมด (GOV-02)
"""

import time
from collections import deque
from datetime import datetime
from pathlib import Path

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

# P4-M1: เสิร์ฟ React UI ที่ /app ถ้า build แล้ว (web/dist) — deployment ชิ้นเดียวกับ API
_WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
if _WEB_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/app", StaticFiles(directory=_WEB_DIST, html=True), name="web")


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


@app.get("/graph/indirect.json")
def graph_indirect(
    a: str = Query(...), b: str = Query(...), max_hops: int = Query(3, le=4)
) -> dict:
    """SIM-10 — ความสัมพันธ์ทางอ้อมระหว่าง 2 entities จาก knowledge graph (หนี้เทคนิค Phase 0)"""
    from graphlayer.store import Neo4jStore

    settings = get_settings()
    try:
        store = Neo4jStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        path = store.query_indirect(a, b, max_hops=max_hops)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"knowledge graph ไม่พร้อม: {e}") from e
    if path is None:
        raise HTTPException(
            status_code=404, detail=f"ไม่พบเส้นทางระหว่าง '{a}' กับ '{b}' ใน {max_hops} hops"
        )
    return {
        "nodes": list(path.nodes),
        "relations": list(path.relations),
        "hops": len(path.relations),
        "note": "ทุก node/edge มี provenance ย้อนถึงเอกสารต้นทางใน graph (NFR-08)",
    }


def _run_dashboard(subject: str, granularity: str, agents: int = 100) -> Dashboard:
    settings = get_settings()
    policy = ElectionPolicy(classify_scenario(subject))
    policy.require_aggregate(granularity)  # GOV-02: individual ถูก block ใน election mode

    # default 100 (quick tier) — ผู้เรียกขอมากขึ้นได้แต่ไม่เกิน cap ต่อ run
    n = min(agents, settings.max_agents_per_run)
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
    agents: int = Query(100, ge=10),
) -> dict:
    try:
        dash = _run_dashboard(subject, granularity, agents)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return dash.to_dict()


@app.get("/dashboard.pdf")
def dashboard_pdf(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    granularity: str = Query("aggregate"),
    agents: int = Query(100, ge=10),
):
    """P4-M2 — Executive Brief เป็น PDF (ผ่านจุด export เดียว + watermark สองชั้น)"""
    from fastapi.responses import FileResponse

    from governance.watermark import export_report

    try:
        dash = _run_dashboard(subject, granularity, agents)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    lo, hi = dash.brief.headline_range
    lines = [
        f"# Executive Brief: {dash.subject}",
        "",
        f"Fragility {dash.brief.fragility_index}/100 — {dash.brief.confidence_label}",
        f"ช่วงผลหลัก: [{lo:+.0%}, {hi:+.0%}] (แสดงเป็นช่วงเสมอ — TRUST-09)",
        "",
        "## ประเด็นหลัก",
    ]
    lines += [f"- {ln.text}" for ln in dash.brief.lines]
    lines += ["", "## เปรียบเทียบ scenario (สัดส่วนผู้เชื่อรายกลุ่ม)", ""]
    segs = sorted({s for sc in dash.scenarios for s in sc.belief_by_segment})
    lines.append("| กลุ่ม | " + " | ".join(sc.name for sc in dash.scenarios) + " |")
    lines.append("|---|" + "---|" * len(dash.scenarios))
    for seg in segs:
        row = " | ".join(f"{sc.belief_by_segment.get(seg, 0):.0%}" for sc in dash.scenarios)
        lines.append(f"| {seg} | {row} |")

    settings = get_settings()
    run_id = f"dashpdf-{datetime.now():%Y%m%d-%H%M%S}"
    # GOV-02: scenario เลือกตั้ง (ระดับ aggregate ที่อนุญาต) ต้องติดป้ายบังคับ 3 ชนิดใน PDF ด้วย
    content = ElectionPolicy(classify_scenario(subject)).apply_labels("\n".join(lines))
    out = export_report(
        content,
        Path(__file__).resolve().parents[1] / ".tmp" / f"{run_id}.pdf",
        run_id=run_id,
        enabled=settings.watermark_enabled,
    )
    return FileResponse(out, media_type="application/pdf", filename=f"chimlang-{run_id}.pdf")


class JobRequest(BaseModel):
    subject: str
    granularity: str = "aggregate"
    agents: int = 100


@app.post("/jobs/whatif")
def submit_job(req: JobRequest) -> dict:
    """P4-M3 — ส่ง simulation เข้าคิว (Celery) แทนการรอใน request (NFR-03)"""
    from core.tasks import celery_app, whatif_dashboard_task

    policy = ElectionPolicy(classify_scenario(req.subject))
    try:
        policy.require_aggregate(req.granularity)  # fail fast ก่อน enqueue
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    agents = min(max(req.agents, 10), get_settings().max_agents_per_run)

    if celery_app.conf.task_always_eager:  # โหมด test — รันทันทีไม่ต้องมี broker
        res = whatif_dashboard_task.apply(args=(req.subject, req.granularity, agents))
        return {"job_id": res.id, "status": "SUCCESS", "result": res.get()}
    try:
        async_res = whatif_dashboard_task.delay(req.subject, req.granularity, agents)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"queue ไม่พร้อม (redis?): {e}") from e
    return {"job_id": async_res.id, "status": async_res.status}


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    from core.tasks import celery_app

    res = celery_app.AsyncResult(job_id)
    body: dict = {"job_id": job_id, "status": res.status}
    if res.successful():
        body["result"] = res.result
    elif res.failed():
        body["error"] = str(res.result)
    return body


@app.get("/runs.json")
def runs_json() -> dict:
    """หน้าการจัดการรัน (P4-M1): รันล่าสุด + คำทำนายที่ครบกำหนดรอ resolve"""
    from datetime import date

    from governance.store import GovernanceStore

    settings = get_settings()
    try:
        store = GovernanceStore(settings.postgres_url)
        store.setup()
        runs = store.recent_runs()
        due = [
            {
                "prediction_id": p.prediction_id,
                "claim": p.claim,
                "domain": p.domain,
                "due_date": p.due_date.isoformat(),
            }
            for p in store.due_unresolved(date.today())
        ]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"runs": runs, "due": due}


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
def signal_json(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    agents: int = Query(100, ge=10),
) -> dict:
    """SIG-01/03/04 — features พร้อมช่วง + metadata บังคับ; election = ปิด (GOV-02)"""
    if not signal_rate_limiter.allow():
        raise HTTPException(status_code=429, detail="rate limit: signal endpoint (SIG-04)")
    policy = ElectionPolicy(classify_scenario(subject))
    try:
        policy.guard_sim_to_signal()  # GOV-02: scenario เลือกตั้ง/การเมือง = signal ปิดตาย
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    settings = get_settings()
    n = min(agents, settings.max_agents_per_run)
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


class CitizenImpactRequest(BaseModel):
    """CIT-01: ตัวเลือกปิดทั้งหมด ≤ 10 ฟิลด์ — ไม่มี free text โดยโครงสร้าง"""

    income_band: str
    region: str
    commute: str
    occupation: str
    age_band: str
    household_size: int


@app.post("/citizen/impact.json")
def citizen_impact(req: CitizenImpactRequest) -> dict:
    """Personal Impact Twin — session-only: ไม่บันทึกอินพุตใดๆ ลง DB (CIT-01/NFR-04)"""
    from simulation.citizen import CitizenInputs, InvalidCitizenInputError, build_impact_twin

    settings = get_settings()
    try:
        inputs = CitizenInputs(**req.model_dump())
    except InvalidCitizenInputError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    twin = build_impact_twin(
        inputs,
        PersonaFactory(),
        max_agents=settings.max_agents_per_run,
        seed=settings.default_seed,
    )
    return twin.to_dict()  # มี CITIZEN_DISCLAIMER เสมอ (CIT-04)


class CitizenFeedbackRequest(BaseModel):
    segment_id: str
    stance: str


@app.post("/citizen/feedback.json")
def citizen_feedback(req: CitizenFeedbackRequest) -> dict:
    """CIT-03 — รับความเห็น (segment+stance เท่านั้น); aggregate ปล่อยเมื่อ n ≥ 20"""
    from simulation.citizen import CITIZEN_DISCLAIMER, FeedbackPool, InvalidCitizenInputError

    settings = get_settings()
    pool = FeedbackPool(settings.postgres_url)
    pool.setup()
    try:
        pool.add(req.segment_id, req.stance)
    except InvalidCitizenInputError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "status": "รับความเห็นแล้ว",
        "k_anonymity_note": "ความเห็นจะแสดงต่อสาธารณะเมื่อกลุ่มของคุณมีผู้ตอบครบ 20 คน",
        "disclaimer": CITIZEN_DISCLAIMER,
    }


@app.get("/citizen/portal.html", response_class=HTMLResponse)
def citizen_portal() -> str:
    """CIT-02 — portal ฉบับประชาชน (ภาษาง่าย + ช่วง + disclaimer ถาวร)"""
    from simulation.citizen import (
        CitizenInputs,
        FeedbackPool,
        apply_feedback_round,
        build_impact_twin,
        render_citizen_portal,
    )

    settings = get_settings()
    factory = PersonaFactory()
    sample = CitizenInputs(
        income_band="15k-30k",
        region="ชานเมือง",
        commute="รถยนต์ส่วนตัว",
        occupation="พนักงานออฟฟิศ",
        age_band="31-45",
        household_size=3,
    )
    twin = build_impact_twin(
        sample, factory, max_agents=settings.max_agents_per_run, seed=settings.default_seed
    )
    pool = FeedbackPool(settings.postgres_url)
    pool.setup()
    aggregates = pool.aggregates()
    effect = apply_feedback_round(
        aggregates, factory, max_agents=settings.max_agents_per_run, seed=settings.default_seed
    )
    md = render_citizen_portal("มาตรการค่าธรรมเนียมรถติด กทม.", twin, aggregates, effect)
    return (
        "<!doctype html><html lang='th'><head><meta charset='utf-8'></head>"
        "<body><pre style='white-space:pre-wrap;font-family:system-ui'>"
        f"{md}</pre></body></html>"
    )


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
