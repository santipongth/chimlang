"""Run readiness and trust score helpers.

These helpers are deterministic and side-effect free. They intentionally do not
call LLMs or external providers; they only estimate and explain whether a run is
ready enough to start.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import Settings, get_settings
from core.llm.budget import spent_this_month
from core.llm.cost import CostEstimator, TierLoad
from core.llm.pricing import UnknownModelPricingError
from core.llm.userconfig import (
    effective_llm_settings,
    effective_monthly_cap,
    effective_pricing,
)
from governance.election import ElectionPolicy, classify_scenario
from governance.pii import PIIDetector, load_allowlist
from simulation.engines import get_engine


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    label: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }


def _status_score(status: str) -> int:
    return {"pass": 1, "warn": 0, "block": -1}.get(status, 0)


def estimate_run_cost(body: dict, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    engine = get_engine(str(body.get("engine", "fabric")))
    agents = min(int(body.get("agents") or 1), engine.max_agents)
    rounds = max(1, min(int(body.get("rounds") or 3), 10))
    if engine.key != "debate":
        return {"estimated_usd": 0.0, "currency": "USD", "calls": 0, "note": "fabric_engine_no_llm"}
    llm_settings = effective_llm_settings()
    pricing = effective_pricing()
    from simulation.debate import ANALYST_SYNTHESIS_MAX_TOKENS, synthesis_retry_ceiling

    synthesis_tokens = int(llm_settings.llm_synthesis_max_tokens or ANALYST_SYNTHESIS_MAX_TOKENS)
    loads = [
        TierLoad(llm_settings.llm_model_crowd, agents * rounds, 900, 160),
        TierLoad(
            llm_settings.llm_model_analyst,
            1,
            9_000,
            synthesis_retry_ceiling(synthesis_tokens),
        ),
    ]
    estimate = CostEstimator(pricing).estimate(loads)
    return {
        "estimated_usd": round(estimate.total_usd, 6),
        "currency": "USD",
        "calls": agents * rounds + 1,
        "run_cap_usd": llm_settings.run_budget_usd_cap,
        "note": "preflight_estimate",
    }


def build_readiness(body: dict, *, election_verified: bool = False) -> dict:
    settings = get_settings()
    checks: list[ReadinessCheck] = []
    subject = str(body.get("subject") or "").strip()
    engine_key = str(body.get("engine") or "fabric")
    try:
        engine = get_engine(engine_key)
        checks.append(ReadinessCheck("engine", "Engine", "pass", engine.label_th))
    except Exception as exc:
        return {
            "can_run": False,
            "checks": [
                ReadinessCheck("engine", "Engine", "block", str(exc)).to_dict(),
            ],
            "cost": {"estimated_usd": 0.0},
        }
    if len(subject) < 4:
        checks.append(ReadinessCheck("subject", "Scenario", "block", "subject_too_short"))
    elif not settings.pii_detector_enabled:
        checks.append(ReadinessCheck("pii", "PII guard", "block", "pii_detector_disabled"))
    else:
        pii = PIIDetector(load_allowlist()).check(subject)
        checks.append(
            ReadinessCheck(
                "pii",
                "PII guard",
                "block" if pii.blocked else "pass",
                "; ".join(pii.block_reasons[:3]) if pii.blocked else "clean",
            )
        )
    election = ElectionPolicy(classify_scenario(subject))
    checks.append(
        ReadinessCheck(
            "election",
            "Election governance",
            "block" if election.active and not election_verified else "pass",
            "verified_admin_required"
            if election.active and not election_verified
            else "aggregate_policy_ready",
        )
    )
    sources = list(body.get("sources") or [])
    if sources and engine.key != "debate":
        checks.append(
            ReadinessCheck("sources", "Sources", "block", "sources_require_debate_engine")
        )
    else:
        checks.append(
            ReadinessCheck(
                "sources",
                "Sources",
                "warn" if engine.key == "debate" and not sources else "pass",
                f"{len(sources)} source(s)",
            )
        )
    live_news = bool(body.get("live_news"))
    if live_news and engine.key != "debate":
        checks.append(
            ReadinessCheck("news", "News Desk", "block", "live_news_requires_debate_engine")
        )
    elif live_news:
        checks.append(
            ReadinessCheck("news", "News Desk", "pass", "rss_or_tavily_will_be_checked_at_run_time")
        )
    else:
        checks.append(ReadinessCheck("news", "News Desk", "warn", "disabled"))
    try:
        cost = estimate_run_cost(body, settings)
        run_cap = float(cost.get("run_cap_usd", settings.run_budget_usd_cap))
        checks.append(
            ReadinessCheck(
                "budget",
                "Run budget",
                "block" if cost["estimated_usd"] > run_cap else "pass",
                f"${cost['estimated_usd']:.4f} / cap ${run_cap:.2f}",
            )
        )
        if engine.key == "debate":
            monthly_spent = spent_this_month(settings.postgres_url)
            monthly_cap = effective_monthly_cap()
            monthly_projected = monthly_spent + cost["estimated_usd"]
            monthly_blocked = monthly_cap > 0 and monthly_projected > monthly_cap
            cost.update(
                {
                    "monthly_spent_usd": round(monthly_spent, 6),
                    "monthly_cap_usd": monthly_cap,
                    "monthly_projected_usd": round(monthly_projected, 6),
                }
            )
            checks.append(
                ReadinessCheck(
                    "monthly_budget",
                    "Monthly budget",
                    "block" if monthly_blocked else "pass",
                    f"${monthly_spent:.2f} + ${cost['estimated_usd']:.4f} / cap ${monthly_cap:.2f}",
                )
            )
    except UnknownModelPricingError as exc:
        cost = {"estimated_usd": 0.0, "error": str(exc)}
        checks.append(ReadinessCheck("budget", "Budget", "block", str(exc)))
    except Exception as exc:
        cost = {"estimated_usd": 0.0, "error": str(exc)}
        checks.append(ReadinessCheck("budget", "Budget", "block", str(exc)))
    can_run = all(_status_score(c.status) >= 0 for c in checks) and not any(
        c.status == "block" for c in checks
    )
    return {"can_run": can_run, "checks": [c.to_dict() for c in checks], "cost": cost}


def build_trust_scorecard(detail: dict) -> dict:
    payload = detail.get("payload") or {}
    checks: list[dict] = []
    # Engine-aware: fabric ($0 mechanistic) มีเฉพาะเช็คที่เกี่ยวจริง — เช็คฝั่ง LLM/debate
    # (sources/news/posts/budget/verifier/judge) ไม่ถูก append จึงไม่เข้าตัวหารคะแนน
    engine_key = str(detail.get("engine") or "")
    try:
        llm_engine = get_engine(engine_key).uses_llm
    except ValueError:
        # engine ที่ไม่รู้จัก: คงชุดเช็คเต็มแบบ conservative (พฤติกรรมเดิม)
        llm_engine = True

    def add(id_: str, label: str, status: str, detail_text: str, weight: int = 1) -> None:
        checks.append(
            {
                "id": id_,
                "label": label,
                "status": status,
                "detail": detail_text,
                "weight": weight,
            }
        )

    add(
        "status",
        "Run lifecycle",
        "pass" if detail.get("status") == "complete" else "warn",
        detail.get("status", "unknown"),
        2,
    )
    if llm_engine:
        sources = list(payload.get("sources") or [])
        blocked_sources = sum(1 for s in sources if s.get("status") in {"blocked", "error"})
        add(
            "sources",
            "Evidence sources",
            "pass"
            if sources and not blocked_sources
            else "warn"
            if not blocked_sources
            else "block",
            f"{len(sources)} sources, {blocked_sources} blocked/error",
            2,
        )
        news_items = list((payload.get("news") or {}).get("items") or [])
        bad_news = sum(1 for n in news_items if n.get("status") in {"blocked", "error"})
        add(
            "news",
            "News Desk",
            "pass" if news_items and not bad_news else "warn" if not bad_news else "block",
            f"{len(news_items)} items, {bad_news} blocked/error",
        )
        metrics = payload.get("metrics") or {}
        failed = int(metrics.get("posts_failed") or 0)
        ok = int(metrics.get("posts_ok") or 0)
        fail_rate = failed / max(1, failed + ok)
        add(
            "parse_failures",
            "Agent output integrity",
            "pass" if fail_rate <= 0.05 else "warn" if fail_rate <= 0.2 else "block",
            f"{failed} failed of {failed + ok} posts",
            2,
        )
        add(
            "budget",
            "Budget accounting",
            # cost_usd หาย = ไม่มีข้อมูลต้นทุน → warn (เดิม get(..., 0) ทำให้ pass เสมอ)
            "pass" if payload.get("cost_usd") is not None else "warn",
            f"${float(payload.get('cost_usd') or 0):.4f}",
        )
    manifest = detail.get("manifest") or {}
    try:
        from core.run_manifest import verify_manifest_hash

        manifest_valid = verify_manifest_hash(manifest)
    except Exception:
        manifest_valid = False
    add(
        "reproducibility",
        "Reproducibility",
        "pass"
        if manifest.get("schema_version") == 1 and manifest.get("complete") and manifest_valid
        else "warn",
        (
            f"manifest={str(manifest.get('manifest_hash', ''))[:12]} · provider-best-effort"
            if manifest_valid and manifest.get("complete")
            else str(manifest.get("reproducibility") or "legacy-incomplete")
        ),
    )
    if llm_engine:
        verifier = (payload.get("protocol") or {}).get("verifier") or {}
        add(
            "deterministic_verifier",
            "Typed move verifier",
            "pass"
            if verifier.get("status") == "pass"
            else "block"
            if verifier.get("status") == "fail"
            else "warn",
            f"{verifier.get('status', 'legacy')} · "
            f"{len(verifier.get('violations') or [])} findings",
            2,
        )
        judge = (payload.get("protocol") or {}).get("analyst_judge") or {}
        add(
            "analyst_judge",
            "Analyst judge",
            "pass" if judge.get("verdict") == "pass" else "warn",
            str(judge.get("verdict") or "legacy/unavailable"),
        )
    total_weight = sum(c["weight"] for c in checks)
    earned = sum(c["weight"] for c in checks if c["status"] == "pass") + 0.5 * sum(
        c["weight"] for c in checks if c["status"] == "warn"
    )
    score = round(100 * earned / max(1, total_weight))
    if score >= 85:
        band = "strong"
    elif score >= 65:
        band = "usable"
    else:
        band = "needs_review"
    return {"score": score, "band": band, "checks": checks}
