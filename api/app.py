"""FastAPI app (Presentation layer) — REST endpoint สำหรับ dashboard + health

Phase 1 ขอบเขต: endpoint อ่านผล what-if ที่รันแล้ว (กลไกล้วน ไม่เรียก LLM ใน request path
เพื่อไม่ให้ HTTP timeout และคุมต้นทุน) + คืน JSON/HTML ที่ประกอบ dashboard

ทุก scenario ถูกตรวจ election mode; response ระดับ individual ถูก block ถ้าเข้าโหมด (GOV-02)
"""

import time
from collections import deque
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.auth import get_principal, require, require_election
from api.dashboard import (
    Dashboard,
    ScenarioColumn,
    build_executive_brief,
    build_risk_heatmap,
)
from api.render import render_dashboard_html
from core.config import get_settings
from governance.election import ElectionModeError, ElectionPolicy, classify_scenario
from governance.rbac import Permission, Principal
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


@app.middleware("http")
async def security_headers(request, call_next):
    """M6 (NFR-05 ขั้นต่ำ): ป้องกัน MIME sniffing / clickjacking — TLS เป็นหน้าที่ reverse proxy"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "chimlang-api"}


@app.get("/health/deep")
def health_deep() -> dict:
    """M6 (NFR-06): สถานะ dependency รายตัวสำหรับ monitoring — ล่มตัวไหนบอกตรงๆ"""
    settings = get_settings()
    components: dict[str, str] = {}
    try:
        import psycopg

        with psycopg.connect(settings.postgres_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        components["postgres"] = "ok"
    except Exception as e:
        components["postgres"] = f"down: {type(e).__name__}"
    try:
        from core.tasks import celery_app

        with celery_app.connection() as conn:
            conn.ensure_connection(max_retries=1, timeout=3)
        components["redis"] = "ok"
    except Exception as e:
        components["redis"] = f"down: {type(e).__name__}"
    try:
        from graphlayer.store import Neo4jStore

        Neo4jStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password).verify()
        components["neo4j"] = "ok"
    except Exception as e:
        components["neo4j"] = f"down: {type(e).__name__}"
    overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"
    return {"status": overall, "components": components}


@app.get("/graph/indirect.json")
def graph_indirect(
    a: str = Query(...),
    b: str = Query(...),
    max_hops: int = Query(3, le=4),
    principal: Principal = Depends(get_principal),
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


@app.get("/graph/summary.json")
def graph_summary_json(
    limit: int = Query(120, ge=10, le=300), principal: Principal = Depends(get_principal)
) -> dict:
    """P5-M6 — snapshot ของ knowledge graph สำหรับ viz (SIM-09: hub/cluster ระดับ entity ข่าว

    ไม่ map บุคคลจริงนอกบริบทข่าว — PII ถูก block ตั้งแต่ ingest แล้ว GOV-01)
    """
    from graphlayer.store import Neo4jStore
    from graphlayer.summary import compute_hubs

    settings = get_settings()
    try:
        store = Neo4jStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        summary = store.graph_summary(limit=limit)
        store.close()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"knowledge graph ไม่พร้อม: {e}") from e
    kinds = sorted({n["kind"] for n in summary["nodes"]})
    return {
        **summary,
        "hubs": compute_hubs(summary["nodes"]),
        "kinds": kinds,
        "note": "ทุก node/edge มี provenance ย้อนถึงเอกสารต้นทาง (NFR-08) — hub = top 15% degree",
    }


@app.get("/insights.json")
def insights_json(principal: Principal = Depends(get_principal)) -> dict:
    """P5-M6 — analytics ข้าม run จาก audit log + prediction registry (อ่านอย่างเดียว)"""
    from governance.store import GovernanceStore

    settings = get_settings()
    try:
        store = GovernanceStore(settings.postgres_url)
        store.setup()
        return store.insights()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e


def _load_pack_factory(pack_id: int | None) -> "PersonaFactory | None":
    """โหลด PersonaFactory จาก persona pack (P5-M7) — pack ไม่พบ = 404"""
    if pack_id is None:
        return None
    from simulation.persona_packs import PackStore, factory_from_pack

    settings = get_settings()
    try:
        store = PackStore(settings.postgres_url)
        store.setup()
        pack = store.get(pack_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return factory_from_pack(pack)


def _run_dashboard(
    subject: str, granularity: str, agents: int = 100, factory: PersonaFactory | None = None
) -> Dashboard:
    settings = get_settings()
    policy = ElectionPolicy(classify_scenario(subject))
    policy.require_aggregate(granularity)  # GOV-02: individual ถูก block ใน election mode

    # default 100 (quick tier) — ผู้เรียกขอมากขึ้นได้แต่ไม่เกิน cap ต่อ run
    n = min(agents, settings.max_agents_per_run)
    factory = factory or PersonaFactory()
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
    # PRD pipeline ขั้น 7: Tipping Points บังคับทุกรายงาน — จาก run ตัวแทน (seed แรก)
    from simulation.tipping import tipping_from_run

    tipping = tuple(
        {"scenario": name, **tp.to_dict()}
        for name, run in (("baseline", base.baseline), ("variant", base.variant))
        for tp in tipping_from_run(run, "rumor")
    )
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
        tipping_points=tipping,
    )
    return dash


@app.get("/dashboard.json")
def dashboard_json(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    granularity: str = Query("aggregate"),
    agents: int = Query(100, ge=10),
    pack_id: int | None = Query(None),  # persona pack ที่ผู้ใช้นิยามเอง (P5-M7)
    principal: Principal = Depends(get_principal),
) -> dict:
    require(principal, Permission.RUN)
    if ElectionPolicy(classify_scenario(subject)).active:
        require_election(principal)  # GOV-06: election เฉพาะ admin ที่ verify
    try:
        dash = _run_dashboard(subject, granularity, agents, factory=_load_pack_factory(pack_id))
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return dash.to_dict()


@app.get("/dashboard.pdf")
def dashboard_pdf(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    granularity: str = Query("aggregate"),
    agents: int = Query(100, ge=10),
    lang: str = Query("th", pattern="^(th|en)$"),
    principal: Principal = Depends(get_principal),
):
    """P4-M2 — Executive Brief เป็น PDF (จุด export เดียว + watermark) | lang=th/en (NFR-09)"""
    require(principal, Permission.RUN)
    require(principal, Permission.EXPORT)
    if ElectionPolicy(classify_scenario(subject)).active:
        require_election(principal)
    from fastapi.responses import FileResponse

    from governance.watermark import export_report

    try:
        dash = _run_dashboard(subject, granularity, agents)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    lo, hi = dash.brief.headline_range
    # NFR-09: หัวข้อรายงาน 2 ภาษา (เนื้อ insight มาจาก simulation ภาษาไทยเสมอ)
    th = lang == "th"
    lines = [
        f"# Executive Brief: {dash.subject}",
        "",
        f"Fragility {dash.brief.fragility_index}/100 — {dash.brief.confidence_label}",
        (
            f"ช่วงผลหลัก: [{lo:+.0%}, {hi:+.0%}] (แสดงเป็นช่วงเสมอ — TRUST-09)"
            if th
            else f"Headline range: [{lo:+.0%}, {hi:+.0%}] (always an interval — TRUST-09)"
        ),
        "",
        "## ประเด็นหลัก" if th else "## Key findings",
    ]
    lines += [f"- {ln.text}" for ln in dash.brief.lines]
    lines += [
        "",
        "## เปรียบเทียบ scenario (สัดส่วนผู้เชื่อรายกลุ่ม)"
        if th
        else "## Scenario comparison (belief share by segment)",
        "",
    ]
    segs = sorted({s for sc in dash.scenarios for s in sc.belief_by_segment})
    head = "กลุ่ม" if th else "Segment"
    lines.append(f"| {head} | " + " | ".join(sc.name for sc in dash.scenarios) + " |")
    lines.append("|---|" + "---|" * len(dash.scenarios))
    for seg in segs:
        row = " | ".join(f"{sc.belief_by_segment.get(seg, 0):.0%}" for sc in dash.scenarios)
        lines.append(f"| {seg} | {row} |")

    # PRD pipeline ขั้น 7: Tipping Points บังคับใน "ทุกรายงาน" — PDF ด้วย (P5 เก็บตก 12 ก.ค.)
    lines += [
        "",
        "## Tipping Points — จุดที่กระแสพลิก" if th else "## Tipping points — narrative flips",
    ]
    if dash.tipping_points:
        for tp in dash.tipping_points:
            lines.append(
                f"- {tp['scenario']} round {tp['round']}: "
                f"{tp['before']:.0%} → {tp['after']:.0%} ({tp['delta']:+.0%})"
            )
    else:
        lines.append(
            "- ไม่พบจุดพลิก (ไม่มี round ที่ความเชื่อเปลี่ยน ≥ 15%) — การแพร่ค่อยเป็นค่อยไป"
            if th
            else "- none detected (no round moved belief ≥ 15%) — diffusion was gradual"
        )

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
def submit_job(req: JobRequest, principal: Principal = Depends(get_principal)) -> dict:
    """P4-M3 — ส่ง simulation เข้าคิว (Celery) แทนการรอใน request (NFR-03)"""
    require(principal, Permission.RUN)
    if ElectionPolicy(classify_scenario(req.subject)).active:
        require_election(principal)
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
def job_status(job_id: str, principal: Principal = Depends(get_principal)) -> dict:
    from core.tasks import celery_app

    res = celery_app.AsyncResult(job_id)
    body: dict = {"job_id": job_id, "status": res.status}
    if res.successful():
        body["result"] = res.result
    elif res.failed():
        body["error"] = str(res.result)
    return body


@app.get("/runs.json")
def runs_json(principal: Principal = Depends(get_principal)) -> dict:
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
            for p in store.due_unresolved(date.today(), include_test=False)
        ]
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"runs": runs, "due": due}


# ---- App settings (P6-M4) ----


@app.get("/settings.json")
def settings_json(principal: Principal = Depends(get_principal)) -> dict:
    from core.appsettings import get_app_settings

    settings = get_settings()
    try:
        data = get_app_settings(settings.postgres_url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    from core.llm.budget import spent_this_month
    from core.llm.pricing import PricingRegistry
    from core.llm.userconfig import (
        LLM_PROVIDERS,
        effective_llm_settings,
        effective_monthly_cap,
    )
    from core.secretbox import mask, master_key_present

    eff = effective_llm_settings()
    # key ที่ active จริง (DB > .env) — แสดงแบบมาสก์เท่านั้น ไม่เคยส่งเต็ม
    key_from_db = bool(data.get("llm_api_key_enc"))
    active_key = eff.llm_api_key.strip()
    yaml_prices = {
        m: {"input_usd_per_m": p.input_usd_per_m, "output_usd_per_m": p.output_usd_per_m}
        for m, p in PricingRegistry.from_yaml()._table.items()
    }
    try:
        spent = round(spent_this_month(settings.postgres_url), 4)
    except Exception:
        spent = 0.0
    # News Desk (P7): ค่าที่ใช้จริง (DB ทับ .env) — Tavily key มาสก์เท่านั้น
    from simulation.newsdesk import effective_news_config

    eff_feeds, eff_tavily = effective_news_config(settings)
    news_cfg = {
        "feeds": eff_feeds,
        "feeds_source": "db"
        if str(data.get("news_rss_feeds", "")).strip()
        else ("env" if settings.news_rss_feeds_list() else "none"),
        "tavily_present": bool(eff_tavily),
        "tavily_masked": mask(eff_tavily) if eff_tavily else "",
        "tavily_source": "db"
        if data.get("tavily_api_key_enc")
        else ("env" if settings.tavily_api_key.strip() else "none"),
    }
    # อย่าคืน ciphertext ของ key ออกไป
    safe = {k: v for k, v in data.items() if k not in ("llm_api_key_enc", "tavily_api_key_enc")}
    return {
        **safe,
        "webhook_configured": bool(settings.alert_webhook_url.strip()),
        "auth_enabled": settings.auth_enabled,
        "caps": {
            "fabric": settings.max_agents_per_run,
            "debate": settings.max_agents_per_debate,
        },
        # LLM ปรับเองได้ (ADR-0006/0007) — key ไม่เคยออกเต็ม (มาสก์เท่านั้น)
        "llm": {
            "providers": [{"key": k, **v} for k, v in LLM_PROVIDERS.items()],
            "key_present": bool(active_key),
            "key_masked": mask(active_key) if active_key else "",
            "key_source": "db" if key_from_db else ("env" if active_key else "none"),
            "master_key_present": master_key_present(),
            "active_base_url": eff.llm_base_url,
            "active_model_crowd": eff.llm_model_crowd,
            "active_model_analyst": eff.llm_model_analyst,
            "env_model_crowd": settings.llm_model_crowd,
            "env_model_analyst": settings.llm_model_analyst,
            "yaml_prices": yaml_prices,
        },
        "budget": {
            "run_cap_effective": eff.run_budget_usd_cap,
            "monthly_cap_effective": effective_monthly_cap(),
            "spent_this_month": spent,
            "env_run_cap": settings.run_budget_usd_cap,
            "env_monthly_cap": settings.monthly_budget_usd_cap,
        },
        "news": news_cfg,
    }


@app.put("/settings.json")
def settings_put(patch: dict, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from core.appsettings import put_app_settings

    settings = get_settings()
    try:
        return put_app_settings(settings.postgres_url, patch)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e


class LlmKeyBody(BaseModel):
    api_key: str  # ว่าง = ลบ key ที่เก็บ (กลับไปใช้ .env)


@app.put("/settings/llm-key")
def settings_llm_key(body: LlmKeyBody, principal: Principal = Depends(get_principal)) -> dict:
    """ตั้ง/ลบ LLM API key แบบเข้ารหัส (ADR-0007) — endpoint แยกเพื่อไม่ให้ key ปน PUT ปกติ

    ต้องสิทธิ์ ADMIN (จัดการ secret) + ต้องมี master key (CHIMLANG_SECRET_KEY) ก่อน
    """
    require(principal, Permission.ADMIN)
    from core.appsettings import set_llm_api_key
    from core.secretbox import MasterKeyMissingError

    settings = get_settings()
    try:
        set_llm_api_key(settings.postgres_url, body.api_key)
    except MasterKeyMissingError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"ok": True, "set": bool(body.api_key.strip())}


@app.put("/settings/tavily-key")
def settings_tavily_key(body: LlmKeyBody, principal: Principal = Depends(get_principal)) -> dict:
    """ตั้ง/ลบ Tavily search key แบบเข้ารหัส (P7 News Desk) — เงื่อนไขเดียวกับ llm-key"""
    require(principal, Permission.ADMIN)
    from core.appsettings import set_tavily_api_key
    from core.secretbox import MasterKeyMissingError

    settings = get_settings()
    try:
        set_tavily_api_key(settings.postgres_url, body.api_key)
    except MasterKeyMissingError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"ok": True, "set": bool(body.api_key.strip())}


# ---- Persistent runs (P6-M1/M2): เลือก engine → รัน → เก็บถาวร → History/Replay ----


class RunBody(BaseModel):
    engine: str = "fabric"  # fabric | debate
    subject: str
    domain: str = "ทั่วไป"
    agents: int = 100
    rounds: int = 3  # ใช้กับ debate เท่านั้น (fabric ใช้ config ภายใน 20)
    pack_id: int | None = None
    red_team: bool = False  # debate: ฝัง adversarial 2 ตัว (fabric ใช้หน้า compare อยู่แล้ว)
    # P6-M3: เอกสารอ้างอิง (เฉพาะ debate) — {kind: text|url|rss, label, url?, text?}
    sources: list[dict] = []
    # เหตุการณ์จริง (ปลดล็อก calibration): ผู้ใช้ตั้งคำทำนายที่วัดผลได้เอง — ว่าง = heuristic
    claim: str = ""
    measurement: str = ""
    due_days: int = 30
    # มุมมองผลลัพธ์ที่จะเปิดใช้ (P6-M6) — RunDetail แสดงเฉพาะ tab เหล่านี้; ว่าง = ครบทุกมุม
    views: list[str] = []
    # News Desk (P7, SIM-11): เปิดโต๊ะข่าวสด (debate เท่านั้น) — agent ได้ข่าวตาม media diet กลุ่มตัวเอง
    live_news: bool = False


@app.get("/engines.json")
def engines_json(principal: Principal = Depends(get_principal)) -> dict:
    from simulation.engines import ENGINES

    return {"engines": [e.to_dict() for e in ENGINES.values()]}


def _register_run_prediction(
    store,
    run_id: str,
    subject: str,
    domain: str,
    payload: dict,
    *,
    claim: str = "",
    measurement: str = "",
    due_days: int = 30,
) -> None:
    """กฎเหล็กข้อ 3: ทุก run ต้องมี prediction ≥1

    ผู้ใช้ตั้ง claim/measurement/due_days เองได้ (เหตุการณ์จริง — จุดปลดล็อก calibration);
    ไม่ตั้ง = heuristic v1: fabric ทิศจาก headline range (confidence ลดตาม fragility),
    debate ทิศจากจุดยืนเฉลี่ยรอบสุดท้าย (confidence จาก synthesis ถูกลดตาม failed แล้ว)
    """
    from datetime import date, timedelta

    from governance.store import Prediction

    if "brief" in payload:  # fabric dashboard payload
        lo, hi = payload["brief"]["headline_range"]
        frag = payload["brief"]["fragility_index"]
        if hi < 0:
            direction, conf = "ลดลง", round(max(0.5, 0.75 * (1 - frag / 100)), 2)
        elif lo > 0:
            direction, conf = "เพิ่มขึ้น", round(max(0.5, 0.75 * (1 - frag / 100)), 2)
        else:
            direction, conf = "ไม่ชัด", 0.5
        auto_claim = f"{subject}: ทิศทาง delta ของความเชื่อจะ{direction}เมื่อทดสอบซ้ำด้วยชุด parameter ใหม่"
    else:  # debate payload
        avg = (payload.get("metrics", {}).get("per_round_avg_stance") or [0])[-1]
        direction = "เพิ่มขึ้น" if avg > 0.15 else "ลดลง" if avg < -0.15 else "ไม่ชัด"
        conf = float(payload.get("synthesis", {}).get("confidence", 0.5))
        auto_claim = f"{subject}: ฉันทามติของวงดีเบตเอนไปทาง '{direction}' และจะคงทิศเมื่อดีเบตซ้ำ"
    store.register_prediction(
        run_id,
        Prediction(
            claim=claim.strip() or auto_claim,
            direction=direction,
            confidence=max(0.01, min(0.99, conf)),
            measurement=measurement.strip() or "ผู้ใช้ป้อนผลจริงเมื่อครบกำหนด (หน้า Calibration ใน /app)",
            due_date=date.today() + timedelta(days=max(1, min(365, due_days))),
            model_version="chimlang-run@p6",
            domain=domain,
        ),
    )


@app.post("/runs")
def run_create(body: RunBody, principal: Principal = Depends(get_principal)) -> dict:
    """สร้าง run ถาวร (P6-M2) — governance ครบ: PII gate, election, audit, prediction, cap"""
    require(principal, Permission.RUN)
    from core.runstore import RunStore, new_run_id
    from governance.pii import PIIDetector, load_allowlist
    from governance.store import GovernanceStore
    from simulation.engines import get_engine

    settings = get_settings()
    try:
        engine = get_engine(body.engine)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    subject = body.subject.strip()
    if len(subject) < 4:
        raise HTTPException(status_code=422, detail="หัวข้อสั้นเกินไป")
    if not settings.pii_detector_enabled:
        raise HTTPException(status_code=503, detail="PII detector ถูกปิด — ปฏิเสธการรัน (GOV-01)")
    pii = PIIDetector(load_allowlist()).check(subject)
    if pii.blocked:
        raise HTTPException(
            status_code=422, detail="พบ PII ในหัวข้อ (GOV-01): " + "; ".join(pii.block_reasons)
        )
    if ElectionPolicy(classify_scenario(subject)).active:
        require_election(principal)

    if body.sources and body.engine != "debate":
        raise HTTPException(status_code=422, detail="sources ใช้ได้กับ engine debate เท่านั้น")
    n = min(body.agents, engine.max_agents)
    rounds = max(1, min(body.rounds, 10)) if body.engine == "debate" else 20
    run_id = new_run_id(body.engine)
    factory = _load_pack_factory(body.pack_id)

    try:
        rstore = RunStore(settings.postgres_url)
        rstore.setup()
        gov = GovernanceStore(settings.postgres_url)
        gov.setup()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e

    valid_views = {"overview", "debate", "canvas", "evidence"}
    views = [v for v in body.views if v in valid_views] or list(valid_views)
    config = {
        "pack_id": body.pack_id,
        "red_team": body.red_team,
        "requested_agents": body.agents,
        "views": views,  # มุมมองที่ผู้ใช้เลือกเปิด (P6-M6)
        "live_news": body.live_news,  # provenance: run นี้ใช้ข่าวสดหรือไม่ (P7)
    }
    rstore.create(
        run_id=run_id,
        engine=body.engine,
        subject=subject,
        domain=body.domain,
        agents=n,
        rounds=rounds,
        seed=settings.default_seed,
        config=config,
    )
    gov.append_audit(
        actor=principal.user_id,
        action="run_started",
        run_id=run_id,
        config_hash="-",
        detail=f"engine={body.engine} agents={n} subject={subject[:60]}",
    )
    try:
        if body.engine == "fabric":
            payload = _run_dashboard(subject, "aggregate", n, factory=factory).to_dict()
        else:
            from simulation.debate import make_debate_adapter, run_debate
            from simulation.persona import PersonaFactory
            from simulation.redteam_population import inject_red_team
            from simulation.sources import retrieve_context

            personas = (factory or PersonaFactory()).sample(
                n, seed=settings.default_seed, max_agents=n
            )
            if body.red_team:
                personas = inject_red_team(personas)
            source_status: list[dict] = []
            if body.sources:
                from simulation.sources import ingest_sources

                source_status = ingest_sources(settings.postgres_url, run_id, body.sources)
            context = retrieve_context(settings.postgres_url, run_id, subject, k=6)
            # News Desk (P7, SIM-11): โต๊ะข่าวกลางดึงข่าวสด → media diet รายกลุ่ม
            segment_news: dict[str, tuple[str, ...]] = {}
            news_fetcher = None
            news_status: dict = {"enabled": False}
            if body.live_news:
                from core.run_context import RunContext
                from simulation.newsdesk import gather, load_items, segment_feed

                ctx = RunContext(run_id=run_id, seed=settings.default_seed)
                seg_mixes = {p.segment_name: p.channel_mix for p in personas}

                def _diet(items) -> dict[str, tuple[str, ...]]:
                    return {
                        seg: tuple(
                            f"{it.title}: {it.content[:250]}"
                            for it in segment_feed(
                                items, mix, subject, k=4, seed=settings.default_seed
                            )
                        )
                        for seg, mix in seg_mixes.items()
                    }

                gather(settings.postgres_url, ctx, queries=[subject])
                all_items = load_items(settings.postgres_url, run_id)
                segment_news = _diet(all_items)

                def news_fetcher(queries: list[str]) -> dict[str, tuple[str, ...]]:
                    # intent ระหว่างรอบ: ค้นเพิ่ม (gate+PII+snapshot ใน gather) → diet ใหม่
                    gather(settings.postgres_url, ctx, feeds=[], queries=queries)
                    return _diet(load_items(settings.postgres_url, run_id))

                news_status = {
                    "enabled": True,
                    "items": [
                        {
                            "provider": it.provider,
                            "title": it.title,
                            "url": it.url,
                            "fetched_at": it.fetched_at,
                            "status": it.status,
                            "error": it.error,
                        }
                        for it in all_items
                    ],
                }
            result = run_debate(
                personas,
                subject=subject,
                rounds=rounds,
                seed=settings.default_seed,
                adapter=make_debate_adapter(n, rounds),
                context_chunks=context,
                segment_news=segment_news,
                news_fetcher=news_fetcher,
            )
            rstore.add_posts(run_id, [p.to_dict() for p in result.posts])
            # งบรวมเดือน (P6-M5): บันทึกยอดจ่ายจริงเพื่อคุมสะสมทั้งเดือน
            from core.llm.budget import record_spend

            record_spend(settings.postgres_url, result.cost_usd, run_id=run_id)
            # อัปเดตรายการข่าวหลังรัน (รวมที่ค้นเพิ่มจาก intent ระหว่างรอบ)
            if news_status.get("enabled"):
                from simulation.newsdesk import load_items as _reload_news

                news_status["items"] = [
                    {
                        "provider": it.provider,
                        "title": it.title,
                        "url": it.url,
                        "fetched_at": it.fetched_at,
                        "status": it.status,
                        "error": it.error,
                    }
                    for it in _reload_news(settings.postgres_url, run_id)
                ]
            payload = {
                "synthesis": result.synthesis,
                "metrics": result.metrics,
                "cost_usd": result.cost_usd,
                "red_team": body.red_team,
                "sources": source_status,
                "context_used": len(context),
                "news": news_status,
            }
        rstore.finish(run_id, payload)
        _register_run_prediction(
            gov,
            run_id,
            subject,
            body.domain,
            payload,
            claim=body.claim,
            measurement=body.measurement,
            due_days=body.due_days,
        )
        gov.finalize_run(run_id)  # ไม่มี prediction = raise (กฎเหล็กข้อ 3)
        gov.append_audit(
            actor=principal.user_id, action="run_completed", run_id=run_id, config_hash="-"
        )
    except HTTPException:
        raise
    except ElectionModeError as e:
        rstore.fail(run_id, str(e))
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        rstore.fail(run_id, str(e))
        raise HTTPException(status_code=502, detail=f"รันไม่สำเร็จ: {e}") from e
    return {"run_id": run_id, "engine": body.engine, "agents": n}


@app.get("/simruns.json")
def simruns_json(
    search: str = Query(""),
    engine: str = Query(""),
    status: str = Query(""),
    principal: Principal = Depends(get_principal),
) -> dict:
    from core.runstore import RunStore

    settings = get_settings()
    try:
        store = RunStore(settings.postgres_url)
        store.setup()
        return {"runs": store.list_runs(search=search, engine=engine, status=status)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e


@app.get("/runs/{run_id}.json")
def run_detail_json(run_id: str, principal: Principal = Depends(get_principal)) -> dict:
    from core.runstore import RunStore

    settings = get_settings()
    try:
        store = RunStore(settings.postgres_url)
        store.setup()
        return store.get(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e


@app.delete("/runs/{run_id}")
def run_delete(run_id: str, principal: Principal = Depends(get_principal)) -> dict:
    """ลบ run ที่เก็บไว้ (operational) — audit การลบ; prediction/audit เดิมคงอยู่ (append-only)"""
    require(principal, Permission.RUN)
    from core.runstore import RunStore
    from governance.store import GovernanceStore

    settings = get_settings()
    try:
        store = RunStore(settings.postgres_url)
        store.setup()
        store.delete(run_id)
        gov = GovernanceStore(settings.postgres_url)
        gov.setup()
        gov.append_audit(
            actor=principal.user_id, action="run_deleted", run_id=run_id, config_hash="-"
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"ok": True}


# ---- Public Gallery (P5-M8, ADR-0004) ----

gallery_rate_limiter = RateLimiter(max_calls=60, window_s=60.0)


class ShareBody(BaseModel):
    subject: str
    agents: int = 100


class VoteBody(BaseModel):
    vote: str  # agree | disagree


@app.post("/gallery/share")
def gallery_share(body: ShareBody, principal: Principal = Depends(get_principal)) -> dict:
    """แชร์ผลรันสู่สาธารณะ — แชร์ = export: ต้อง EXPORT + ผ่านด่าน ADR-0004 ทุกข้อ"""
    require(principal, Permission.EXPORT)
    from governance.gallery import GalleryStore, guard_share
    from governance.store import GovernanceStore
    from governance.watermark import WatermarkDisabledError

    settings = get_settings()
    try:
        guard_share(body.subject)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except WatermarkDisabledError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    payload = _run_dashboard(body.subject, "aggregate", body.agents).to_dict()
    try:
        store = GalleryStore(settings.postgres_url)
        store.setup()
        token = store.share(
            subject=body.subject.strip(),
            agents=min(body.agents, settings.max_agents_per_run),
            payload=payload,
            created_by=principal.user_id,
        )
        gov = GovernanceStore(settings.postgres_url)
        gov.setup()
        gov.append_audit(
            actor=principal.user_id,
            action="gallery_shared",
            run_id=f"gallery-{token[:12]}",
            config_hash="-",
            detail=f"subject={body.subject[:80]}",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"share_token": token, "url": f"/app/#gallery/{token}"}


@app.get("/gallery.json")
def gallery_list() -> dict:
    """รายการแชร์สาธารณะ — เปิดอ่านได้ทุกคน (precedent: citizen endpoints)"""
    from governance.gallery import GalleryStore

    settings = get_settings()
    try:
        store = GalleryStore(settings.postgres_url)
        store.setup()
        items = store.list_public()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {
        "items": [
            {
                "share_token": i.share_token,
                "subject": i.subject,
                "agents": i.agents,
                "created_at": i.created_at,
                "votes": i.votes,
                "watermark": i.watermark,
                "brief": i.payload.get("brief", {}),
            }
            for i in items
        ],
        "disclaimer": "AI simulation — not a real poll | ทุกตัวเลขเป็นผลจำลอง ไม่ใช่โพลจริง",
    }


@app.get("/gallery/{token}.json")
def gallery_detail(token: str) -> dict:
    from governance.gallery import GalleryStore

    settings = get_settings()
    try:
        store = GalleryStore(settings.postgres_url)
        store.setup()
        item = store.get(token)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {
        "share_token": item.share_token,
        "subject": item.subject,
        "agents": item.agents,
        "created_at": item.created_at,
        "payload": item.payload,
        "watermark": item.watermark,
        "votes": item.votes,
    }


@app.post("/gallery/{token}/vote")
def gallery_vote(token: str, body: VoteBody, request: Request) -> dict:
    """โหวตสาธารณะ (ไม่ต้องมี key) — dedup ด้วย hash ทางเดียว ไม่เก็บ ip ดิบ (ADR-0004)"""
    if not gallery_rate_limiter.allow():
        raise HTTPException(status_code=429, detail="โหวตถี่เกินไป — ลองใหม่ในอีกสักครู่")
    from governance.gallery import GalleryStore, voter_hash

    settings = get_settings()
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    try:
        store = GalleryStore(settings.postgres_url)
        store.setup()
        votes = store.vote(token, body.vote, voter_hash(ip, ua))
    except ValueError as e:
        raise HTTPException(status_code=404 if "ไม่พบ" in str(e) else 422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"votes": votes}


@app.delete("/gallery/{token}")
def gallery_unshare(token: str, principal: Principal = Depends(get_principal)) -> dict:
    """ถอนจากสาธารณะ (record คงอยู่เพื่อ audit) — ต้อง EXPORT เช่นเดียวกับตอนแชร์"""
    require(principal, Permission.EXPORT)
    from governance.gallery import GalleryStore
    from governance.store import GovernanceStore

    settings = get_settings()
    try:
        store = GalleryStore(settings.postgres_url)
        store.setup()
        store.unshare(token)
        gov = GovernanceStore(settings.postgres_url)
        gov.setup()
        gov.append_audit(
            actor=principal.user_id,
            action="gallery_unshared",
            run_id=f"gallery-{token[:12]}",
            config_hash="-",
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"ok": True}


# ---- Persona Packs (P5-M7) ----


class PackBody(BaseModel):
    label: str
    segments: list[dict]
    prompt: str = ""


class PackGenerateBody(BaseModel):
    label: str
    prompt: str


class TryAskBody(BaseModel):
    segment: dict
    question: str


@app.get("/personas/pool.json")
def personas_pool_json(
    pack_id: int | None = Query(None), principal: Principal = Depends(get_principal)
) -> dict:
    """พูลของ persona (P6-M6) — segments + สัดส่วนที่จะใช้จริงในรัน (default สำมะโน หรือ pack)"""
    settings = get_settings()
    if pack_id is not None:
        from simulation.persona_packs import PackStore

        try:
            store = PackStore(settings.postgres_url)
            store.setup()
            pack = store.get(pack_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
        segments, source = pack.segments, f"pack:{pack.label}"
    else:
        segments = PersonaFactory().segments
        source = "census"
    return {
        "source": source,
        "segments": [
            {
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "share": s.get("share", 0),
                "cultural_priors": s.get("cultural_priors", {}),
                "channel_mix": s.get("channel_mix", {}),
                "traits": s.get("traits", []),
            }
            for s in segments
        ],
    }


@app.get("/personas/packs.json")
def personas_packs_json(principal: Principal = Depends(get_principal)) -> dict:
    from simulation.persona_packs import PackStore

    settings = get_settings()
    try:
        store = PackStore(settings.postgres_url)
        store.setup()
        return {"packs": [p.__dict__ for p in store.list_packs()]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e


@app.post("/personas/packs")
def personas_pack_create(body: PackBody, principal: Principal = Depends(get_principal)) -> dict:
    """สร้าง pack เอง — validate + PII gate (GOV-01) ด่านเดียวกับ AI-generate"""
    require(principal, Permission.RUN)
    from simulation.persona_packs import PackStore, PackValidationError

    settings = get_settings()
    try:
        store = PackStore(settings.postgres_url)
        store.setup()
        pack_id = store.create(
            label=body.label.strip(),
            segments=body.segments,
            prompt=body.prompt,
            created_by=principal.user_id,
        )
    except PackValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"id": pack_id}


@app.post("/personas/packs/generate")
def personas_pack_generate(
    body: PackGenerateBody, principal: Principal = Depends(get_principal)
) -> dict:
    """AI-generate pack จาก prompt (analyst tier ผ่าน BudgetGuard) — คืน preview ยังไม่บันทึก

    ผู้ใช้ตรวจ segments ก่อนแล้วค่อยกดบันทึกผ่าน POST /personas/packs (มนุษย์อยู่ใน loop)
    """
    require(principal, Permission.RUN)
    from simulation.persona_ai import generate_pack_from_prompt
    from simulation.persona_packs import PackValidationError

    try:
        segments = generate_pack_from_prompt(body.prompt.strip(), label=body.label.strip())
    except PackValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM ไม่พร้อมหรือ generate ไม่สำเร็จ: {e}") from e
    return {"label": body.label, "prompt": body.prompt, "segments": segments}


@app.post("/personas/try-ask")
def personas_try_ask(body: TryAskBody, principal: Principal = Depends(get_principal)) -> dict:
    """ลอง ask: segment เดียวตอบ 1 คำถาม (crowd + reasoning=False) — preview ก่อนรันเต็ม"""
    require(principal, Permission.RUN)
    from simulation.persona_ai import try_ask

    if len(body.question.strip()) < 4:
        raise HTTPException(status_code=422, detail="คำถามสั้นเกินไป")
    try:
        answer = try_ask(body.segment, body.question.strip())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM ไม่พร้อม: {e}") from e
    return {"answer": answer, "segment": body.segment.get("name", "")}


@app.delete("/personas/packs/{pack_id}")
def personas_pack_delete(pack_id: int, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    from simulation.persona_packs import PackStore

    settings = get_settings()
    try:
        store = PackStore(settings.postgres_url)
        store.setup()
        store.delete(pack_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"ok": True}


class WatchlistBody(BaseModel):
    label: str
    subject: str
    agents: int = 100
    cadence: str = "daily"  # daily | weekly


@app.get("/watchlists.json")
def watchlists_json(principal: Principal = Depends(get_principal)) -> dict:
    """P5-M5 — รายการ watchlist + alerts (unread count สำหรับ badge ที่ sidebar)"""
    from governance.watchlist import WatchlistStore

    settings = get_settings()
    try:
        store = WatchlistStore(settings.postgres_url)
        store.setup()
        items = [w.__dict__ for w in store.list_watchlists()]
        alerts = store.list_alerts(limit=50)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {
        "items": items,
        "alerts": alerts,
        "unread": sum(1 for a in alerts if not a["read"]),
        "webhook_configured": bool(settings.alert_webhook_url.strip()),
    }


@app.post("/watchlists")
def watchlist_create(body: WatchlistBody, principal: Principal = Depends(get_principal)) -> dict:
    require(principal, Permission.RUN)
    if ElectionPolicy(classify_scenario(body.subject)).active:
        require_election(principal)  # GOV-02/06: election watchlist เฉพาะ admin verified
    from governance.watchlist import WatchlistStore

    settings = get_settings()
    try:
        store = WatchlistStore(settings.postgres_url)
        store.setup()
        wid = store.create(
            label=body.label.strip() or body.subject[:40],
            subject=body.subject.strip(),
            agents=min(body.agents, settings.max_agents_per_run),
            cadence=body.cadence,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"id": wid}


@app.post("/watchlists/{watchlist_id}/toggle")
def watchlist_toggle(
    watchlist_id: int, active: bool = Query(...), principal: Principal = Depends(get_principal)
) -> dict:
    require(principal, Permission.RUN)
    from governance.watchlist import WatchlistStore

    settings = get_settings()
    try:
        store = WatchlistStore(settings.postgres_url)
        store.setup()
        store.set_active(watchlist_id, active)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"id": watchlist_id, "active": active}


@app.post("/watchlists/{watchlist_id}/run")
def watchlist_run_now(watchlist_id: int, principal: Principal = Depends(get_principal)) -> dict:
    """Run now — ตรวจทันทีไม่รอ cadence (กลไกล้วน $0 — cap ยังคุม n เสมอ)"""
    require(principal, Permission.RUN)
    from governance.watchlist import WatchlistStore, check_watchlist, default_runner

    settings = get_settings()
    try:
        store = WatchlistStore(settings.postgres_url)
        store.setup()
        w = store.get(watchlist_id)
        if ElectionPolicy(classify_scenario(w.subject)).active:
            require_election(principal)
        created = check_watchlist(store, w, runner=default_runner)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"id": watchlist_id, "alerts_created": created}


class AlertReadBody(BaseModel):
    id: int | None = None
    all: bool = False


@app.post("/alerts/read")
def alerts_read(body: AlertReadBody, principal: Principal = Depends(get_principal)) -> dict:
    from governance.watchlist import WatchlistStore

    settings = get_settings()
    try:
        store = WatchlistStore(settings.postgres_url)
        store.setup()
        store.mark_read(body.id, all_alerts=body.all)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e
    return {"ok": True}


@app.get("/compare.json")
def compare_json(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    agents: int = Query(100, ge=10),
    pack_id: int | None = Query(None),
    principal: Principal = Depends(get_principal),
) -> dict:
    """P5-M4 — เทียบ baseline vs +Red Team (seed เดียวกัน): ข้อสรุปทนต่อ adversarial ไหม

    governance เดียวกับ dashboard: ต้อง RUN, election scenario ต้อง admin verified (GOV-02/06)
    """
    require(principal, Permission.RUN)
    if ElectionPolicy(classify_scenario(subject)).active:
        require_election(principal)
    from simulation.compare import run_redteam_compare

    settings = get_settings()
    n = min(agents, settings.max_agents_per_run)
    result = run_redteam_compare(
        _load_pack_factory(pack_id) or PersonaFactory(),
        n_agents=n,
        max_agents=n,
        rounds=20,
        base_messages=[Message("rumor", "rumor", RUMOR, 1, "public_feed")],
        event=Message("official", "correction", EVENT, 8, "public_feed", counters="rumor"),
        target_msg_id="rumor",
        seeds=[settings.default_seed + i for i in range(4)],
    )
    return {"subject": subject, **result}


@app.get("/calibration.json")
def calibration_json(principal: Principal = Depends(get_principal)) -> dict:
    """หน้า Calibration (P5-M3): Brier รวม/รายโดเมน + trend รายสัปดาห์ + คิว resolve

    อ่านอย่างเดียว — แค่ authenticate (viewer ดูได้ เหมือน /runs.json)
    """
    from datetime import date

    from governance.store import GovernanceStore

    settings = get_settings()
    try:
        store = GovernanceStore(settings.postgres_url)
        store.setup()
        # UI ไม่โชว์ขยะจาก test suite (domain ทดสอบ%) — registry ลบไม่ได้จึงกรองที่ชั้นอ่าน
        return store.calibration_detail(date.today(), include_test=False)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {e}") from e


class ResolveBody(BaseModel):
    outcome: str  # "true" | "partial" | "false"
    note: str = ""


@app.post("/predictions/{prediction_id}/resolve")
def resolve_prediction_api(
    prediction_id: int,
    body: ResolveBody,
    principal: Principal = Depends(get_principal),
) -> dict:
    """Resolve คำทำนาย (TRUST-02) — append-only: บันทึกแล้วแก้ไม่ได้ (TRUST-01)

    partial = เกิดขึ้นบางส่วน → outcome_value 0.5 ใน Brier | ต้องสิทธิ์ RUN (analyst ขึ้นไป)
    """
    require(principal, Permission.RUN)
    values = {"true": 1.0, "partial": 0.5, "false": 0.0}
    if body.outcome not in values:
        raise HTTPException(status_code=422, detail="outcome ต้องเป็น true/partial/false")
    from governance.store import GovernanceStore

    settings = get_settings()
    try:
        store = GovernanceStore(settings.postgres_url)
        store.setup()
        brier = store.resolve_prediction(
            prediction_id,
            outcome=values[body.outcome],
            resolver=principal.user_id,
            note=body.note,
        )
        store.append_audit(
            actor=principal.user_id,
            action="prediction_resolved",
            run_id=f"prediction-{prediction_id}",
            config_hash="-",
            detail=f"outcome={body.outcome} brier={brier:.3f} note={body.note[:120]}",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        msg = str(e)
        if "duplicate key" in msg or "prediction_resolution_prediction_id_key" in msg:
            # UNIQUE ที่ DB: resolve ซ้ำ = แก้ผลย้อนหลัง — ห้ามตามกฎเหล็กข้อ 3
            raise HTTPException(
                status_code=409,
                detail=f"prediction {prediction_id} ถูก resolve ไปแล้ว — แก้ผลไม่ได้ (TRUST-01)",
            ) from e
        raise HTTPException(status_code=503, detail=f"ฐานข้อมูลไม่พร้อม: {msg}") from e
    return {"prediction_id": prediction_id, "outcome": body.outcome, "brier": round(brier, 4)}


@app.get("/dashboard.html", response_class=HTMLResponse)
def dashboard_html(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    granularity: str = Query("aggregate"),
    principal: Principal = Depends(get_principal),
) -> str:
    require(principal, Permission.RUN)
    if ElectionPolicy(classify_scenario(subject)).active:
        require_election(principal)
    try:
        dash = _run_dashboard(subject, granularity)
    except ElectionModeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return render_dashboard_html(dash)


@app.get("/signal.json")
def signal_json(
    subject: str = Query("มาตรการค่าธรรมเนียมรถติด กทม."),
    agents: int = Query(100, ge=10),
    principal: Principal = Depends(get_principal),
) -> dict:
    """SIG-01/03/04 — features พร้อมช่วง + metadata บังคับ; election = ปิด (GOV-02)"""
    require(principal, Permission.RUN)
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
