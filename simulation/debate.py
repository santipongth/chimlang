"""Debate engine (P6-M1) — agent LLM โพสต์โต้กันเป็นรอบ (แนวคิด GraphRAG Swarm ของ SwarmSight)

จุดที่เข้มกว่าต้นแบบ (ตามกติกา PHASE6-BRIEF):
- **seeded ทุกจุดสุ่ม**: การ sample โพสต์รอบก่อนใช้ Random(seed) เดียว draw ตามลำดับ
  ใน main thread ก่อน dispatch — run เดิม seed เดิม = feed เดิม (ตัว LLM pin seed แบบ
  best-effort ผ่าน OpenRouter — ข้อจำกัดเดียวกับ extraction, snapshot จริงคือ posts ที่เก็บ)
- **fail-closed**: parse พัง/call พัง = โพสต์ติดธง failed — ไม่ปนใน metrics/synthesis
  (ต้นแบบนับ stance 0 ต่อเงียบๆ = silent corruption)
- ทุก call ผ่าน adapter + BudgetGuard, ประเมิน cost ก่อนเริ่ม; crowd ใช้ reasoning=False
  (บทเรียน 6 ก.ค. — เร็ว 29x); synthesis ใช้ analyst + mechanical fallback
- ภาษาไทย first-class + กติกา prompt มาตรฐาน (ห้ามกุชื่อ/ตัวเลข)
"""

import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from random import Random

from core.config import get_settings
from core.llm.adapter import LLMAdapter, ModelTier
from core.llm.cost import BudgetGuard, CostEstimator, TierLoad
from core.text import sanitize_llm_text
from simulation.persona import Persona
from simulation.tipping import detect_tipping_points

DEFAULT_ROUNDS = 3
REPLY_SAMPLE = 6
MAX_POST_CHARS = 400


class DebateUnavailableError(RuntimeError):
    """Raised when no agent response is usable, so no prediction can be trusted."""


@dataclass(frozen=True)
class DebatePost:
    round_no: int
    agent_idx: int
    segment: str
    content: str
    stance: float
    sentiment: float
    failed: bool = False
    failure_reason: str = ""
    want_to_know: str = ""  # query intent (P7-M3) — สิ่งที่ agent อยากรู้เพิ่ม → โต๊ะข่าวค้นให้

    def to_dict(self) -> dict:
        return {
            "round_no": self.round_no,
            "agent_idx": self.agent_idx,
            "segment": self.segment,
            "content": self.content,
            "stance": round(self.stance, 4),
            "sentiment": round(self.sentiment, 4),
            "failed": self.failed,
            "failure_reason": self.failure_reason,
            "want_to_know": self.want_to_know,
        }


@dataclass(frozen=True)
class DebateResult:
    posts: tuple[DebatePost, ...]
    synthesis: dict
    metrics: dict
    protocol: dict
    failed_posts: int
    cost_usd: float

    @property
    def ok_posts(self) -> list[DebatePost]:
        return [p for p in self.posts if not p.failed]


def make_debate_adapter(agents: int, rounds: int) -> LLMAdapter:
    """adapter พร้อม estimate เฉพาะงาน debate — เกิน cap (ต่อรัน/รวมเดือน) = ไม่เริ่ม

    ใช้ค่าจากหน้าตั้งค่า (provider/model/ราคา/key/งบ) ถ้าผู้ใช้ตั้งไว้ (ADR-0006/0007)
    """
    from core.llm.budget import check_monthly_budget
    from core.llm.userconfig import (
        effective_llm_settings,
        effective_monthly_cap,
        effective_pricing,
    )

    settings = effective_llm_settings()
    pricing = effective_pricing()
    estimate = CostEstimator(pricing).estimate(
        [
            TierLoad(settings.llm_model_crowd, agents * rounds, 900, 160),
            TierLoad(settings.llm_model_analyst, 1, 1500, 800),
        ]
    )
    # งบรวมเดือน (P6-M5) ก่อน — ยอดสะสม + estimate เกิน = block
    check_monthly_budget(settings.postgres_url, estimate.total_usd, effective_monthly_cap())
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(estimate)  # งบต่อรัน
    return LLMAdapter(settings, pricing, guard)


def _initial_stance(p: Persona) -> float:
    # Red Team ใน debate: จุดยืนตั้งต้นแบบ SwarmSight (contrarian −0.6, auditor −0.3)
    if "contrarian" in p.traits:
        return -0.6
    if "auditor" in p.traits:
        return -0.3
    return 0.0


def _persona_system(p: Persona) -> str:
    role = ""
    if "redteam" in p.traits:
        role = " บทบาทพิเศษของคุณ: ตั้งคำถามกับฉันทามติที่กำลังก่อตัว หาจุดอ่อนของข้อสรุป"
    return (
        f"คุณคือคนไทยกลุ่ม '{p.segment_name}' "
        f"(เกรงใจ {p.kreng_jai:.1f}, ช่องว่างพูด-ทำ {p.say_do_gap:.1f}, "
        f"ใช้มีม/ประชด {p.sarcasm_meme:.1f}) "
        f"ลักษณะ: {', '.join(p.traits) or 'ไม่ระบุ'}.{role} "
        "ตอบภาษาไทยเท่านั้น ห้ามกุชื่อ/ตัวเลข — จำไม่ได้ให้บอกว่าไม่แน่ใจ เรียกคนด้วยบทบาท "
        "ตอบเป็น JSON ล้วนเท่านั้น (ไม่มี markdown)"
    )


def _parse_post(text: str) -> tuple[str, float, float, str]:
    clean = sanitize_llm_text(text)
    clean = re.sub(r"^```(?:json)?|```$", "", clean.strip(), flags=re.MULTILINE).strip()
    data = json.loads(clean)
    content = str(data["content"]).strip()[:MAX_POST_CHARS]
    if not content:
        raise ValueError("content ว่าง")
    stance = max(-1.0, min(1.0, float(data["stance"])))
    sentiment = max(-1.0, min(1.0, float(data.get("sentiment", 0))))
    want = str(data.get("want_to_know", "")).strip()[:120]
    return content, stance, sentiment, want


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return "json_parse_error"
    if isinstance(exc, KeyError):
        return "schema_missing_field"
    if isinstance(exc, (TypeError, ValueError)):
        return "schema_value_error"
    by_exception = {
        "APIConnectionError": "llm_connection_error",
        "APITimeoutError": "llm_timeout",
        "RateLimitError": "llm_rate_limit",
        "AuthenticationError": "llm_auth_error",
        "PermissionDeniedError": "llm_permission_error",
        "NotFoundError": "llm_model_not_found",
        "BadRequestError": "llm_bad_request",
        "InternalServerError": "llm_provider_error",
    }
    if reason := by_exception.get(type(exc).__name__):
        return reason
    return "llm_call_error"


def _compute_metrics(posts: list[DebatePost], rounds: int, agent_count: int) -> dict:
    ok = [p for p in posts if not p.failed]
    per_round_avg: list[float] = []
    for r in range(rounds):
        rs = [p.stance for p in ok if p.round_no == r]
        per_round_avg.append(sum(rs) / len(rs) if rs else 0.0)
    last = [p.stance for p in ok if p.round_no == rounds - 1]
    dispersion = statistics.pstdev(last) if len(last) > 1 else 0.0
    # tipping: map stance [-1,1] → [0,1] แล้วใช้ detector เดิม (threshold 0.15 ของ share
    # = 0.30 บนสเกล stance — สอดคล้อง SwarmSight ที่ใช้ 0.25)
    series = [(s + 1) / 2 for s in per_round_avg]
    tipping = [tp.to_dict() for tp in detect_tipping_points(series)] if len(series) > 1 else []
    return {
        "per_round_avg_stance": [round(s, 4) for s in per_round_avg],
        "final_dispersion": round(dispersion, 4),
        "tipping_points": tipping,
        "posts_ok": len(ok),
        "posts_failed": len(posts) - len(ok),
        "agent_count": agent_count,
    }


def analyze_protocol(posts: list[DebatePost], *, subject: str, rounds: int) -> dict:
    ok = [p for p in posts if not p.failed]
    terms = [w for w in re.findall(r"[\w\u0E00-\u0E7F]{4,}", subject) if len(w.strip()) >= 4][:6]
    per_round = []
    for r in range(rounds):
        rs = [p.stance for p in ok if p.round_no == r]
        avg = sum(rs) / len(rs) if rs else 0.0
        dispersion = statistics.pstdev(rs) if len(rs) > 1 else 0.0
        per_round.append(
            {
                "round": r,
                "avg_stance": round(avg, 4),
                "dispersion": round(dispersion, 4),
                "support": sum(1 for s in rs if s > 0.2),
                "neutral": sum(1 for s in rs if -0.2 <= s <= 0.2),
                "oppose": sum(1 for s in rs if s < -0.2),
            }
        )
    by_segment: dict[str, list[float]] = {}
    for p in ok:
        by_segment.setdefault(p.segment, []).append(p.stance)
    nodes = [
        {"segment": seg, "avg_stance": round(sum(vals) / len(vals), 4), "posts": len(vals)}
        for seg, vals in sorted(by_segment.items())
        if vals
    ]
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            gap = abs(float(a["avg_stance"]) - float(b["avg_stance"]))
            if gap >= 0.35:
                edges.append({"from": a["segment"], "to": b["segment"], "tension": round(gap, 4)})
    failures: dict[str, int] = {}
    for p in posts:
        if p.failed:
            key = p.failure_reason or "unknown_failure"
            failures[key] = failures.get(key, 0) + 1
    return {
        "claim_decomposition": {
            "main_claim": subject,
            "facets": terms or [subject[:80]],
            "method": "deterministic_subject_terms",
        },
        "per_round_disagreement": per_round,
        "contention_graph": {"nodes": nodes, "edges": edges},
        "failure_taxonomy": failures,
    }


def _mechanical_synthesis(posts: list[DebatePost], subject: str, rounds: int) -> dict:
    ok = [p for p in posts if not p.failed and p.round_no == rounds - 1]
    n = len(ok) or 1
    avg = sum(p.stance for p in ok) / n
    pos = sum(1 for p in ok if p.stance > 0.2)
    neg = sum(1 for p in ok if p.stance < -0.2)
    lean = "เอนไปทางเห็นด้วย" if avg > 0.15 else "เอนไปทางคัดค้าน" if avg < -0.15 else "เสียงแตก"
    return {
        "summary": f"หัวข้อ '{subject}': หลังดีเบต {rounds} รอบ วงสนทนา{lean} (จุดยืนเฉลี่ย {avg:+.2f})",
        "confidence": round(min(0.9, 0.5 + abs(avg) / 2), 2),
        "distribution": [
            {"bucket": "เห็นด้วย", "pct": round(pos / n * 100)},
            {"bucket": "กลางๆ", "pct": round((n - pos - neg) / n * 100)},
            {"bucket": "คัดค้าน", "pct": round(neg / n * 100)},
        ],
        "key_drivers": ["(สรุปเชิงกลไก — analyst model ไม่พร้อม)"],
        "risks": ["synthesis เป็น fallback เชิงกลไก ไม่ใช่บทวิเคราะห์ LLM"],
        "fallback": True,
    }


def synthesize_snapshot(posts: list[dict], *, subject: str, rounds: int) -> dict:
    """Rebuild debate metrics/synthesis from stored posts only.

    This is the safe partial-retry path for UI/API repair: it never calls an LLM and
    therefore preserves replay reproducibility and budget guarantees.
    """
    debate_posts = [
        DebatePost(
            round_no=int(p["round_no"]),
            agent_idx=int(p["agent_idx"]),
            segment=str(p["segment"]),
            content=str(p.get("content", "")),
            stance=float(p.get("stance", 0.0)),
            sentiment=float(p.get("sentiment", 0.0)),
            failed=bool(p.get("failed", False)),
            failure_reason=str(p.get("failure_reason", "")),
        )
        for p in posts
    ]
    effective_rounds = max(1, rounds or (max((p.round_no for p in debate_posts), default=0) + 1))
    agent_count = len({p.agent_idx for p in debate_posts})
    metrics = _compute_metrics(debate_posts, effective_rounds, agent_count)
    synthesis = _mechanical_synthesis(debate_posts, subject, effective_rounds)
    failed = metrics["posts_failed"]
    total = len(debate_posts) or 1
    synthesis["confidence"] = round(
        float(synthesis.get("confidence", 0.5)) * (1 - failed / total), 2
    )
    synthesis["resynthesized_from_snapshot"] = True
    protocol = analyze_protocol(debate_posts, subject=subject, rounds=effective_rounds)
    return {"synthesis": synthesis, "metrics": metrics, "protocol": protocol}


def run_debate(
    personas: list[Persona],
    *,
    subject: str,
    rounds: int = DEFAULT_ROUNDS,
    seed: int,
    adapter: LLMAdapter,
    context_chunks: tuple[str, ...] = (),
    segment_news: dict[str, tuple[str, ...]] | None = None,
    news_fetcher=None,  # callable(list[str]) -> dict[segment, tuple[str,...]] — โต๊ะข่าวค้นตาม intent
    on_round=None,
) -> DebateResult:
    settings = get_settings()
    if len(personas) > settings.max_agents_per_debate:
        raise ValueError(
            f"debate จำกัด {settings.max_agents_per_debate} agents/run "
            f"(ขอ {len(personas)}) — ทุก agent = LLM call ต่อรอบ"
        )
    rng = Random(seed)
    stances = [_initial_stance(p) for p in personas]
    all_posts: list[DebatePost] = []
    news: dict[str, tuple[str, ...]] = dict(segment_news or {})  # media diet รายกลุ่ม (P7)
    context_block = (
        "\n".join(f"[{i + 1}] {c[:600]}" for i, c in enumerate(context_chunks[:6]))
        if context_chunks
        else "(ไม่มีเอกสารอ้างอิง — ใช้มุมมองของกลุ่มคุณ)"
    )
    spent_before = adapter._guard.spent_usd if hasattr(adapter, "_guard") else 0.0

    for r in range(rounds):
        prev = [p for p in all_posts if p.round_no == r - 1 and not p.failed]
        # sample feed ต่อ agent แบบ deterministic — draw ทั้งหมดใน main thread ตามลำดับ agent
        feeds: list[str] = []
        for idx in range(len(personas)):
            pool = [p for p in prev if p.agent_idx != idx]
            chosen = pool if len(pool) <= REPLY_SAMPLE else rng.sample(pool, REPLY_SAMPLE)
            feeds.append(
                "\n".join(f"- [{p.segment} | จุดยืน {p.stance:+.2f}]: {p.content}" for p in chosen)
                or "(ยังไม่มีโพสต์ก่อนหน้า — นี่คือรอบเปิด แสดงมุมมองตั้งต้นของคุณ)"
            )

        # ฟีดข่าวของกลุ่ม (media diet — P7): แต่ละ segment เห็นชุดข่าวไม่เหมือนกัน
        news_snapshot = dict(news)  # freeze ต่อรอบ ให้ทุก thread เห็นชุดเดียวกัน

        def ask(
            idx: int, r: int = r, feeds: list[str] = feeds, news_now: dict = news_snapshot
        ) -> DebatePost:  # bind ค่าปัจจุบันของ loop
            p = personas[idx]
            seg_news = news_now.get(p.segment_name, ())
            news_block = (
                "\nข่าวล่าสุดที่คนกลุ่มคุณเห็นในฟีดตัวเอง:\n"
                + "\n".join(f"• {ln[:300]}" for ln in seg_news[:4])
                + "\n"
                if seg_news
                else ""
            )
            want_hint = (
                ', "want_to_know": "สิ่งที่อยากรู้เพิ่มก่อนตัดสินใจ (สั้นๆ หรือเว้นว่าง)"' if news_fetcher else ""
            )
            user = (
                f"หัวข้อดีเบต: {subject}\n\n"
                f"ข้อมูลอ้างอิง:\n{context_block}\n{news_block}\n"
                f"จุดยืนปัจจุบันของคุณ: {stances[idx]:+.2f} (−1 คัดค้านสุด … +1 เห็นด้วยสุด)\n\n"
                f"โพสต์ล่าสุดจากคนอื่น (รอบ {r}):\n{feeds[idx]}\n\n"
                "เขียนโพสต์ 1 โพสต์ (ไม่เกิน 60 คำ) ตามเสียงของกลุ่มคุณ — โต้ตอบประเด็น/โพสต์อื่นได้\n"
                'ตอบ JSON: {"content": "ข้อความโพสต์", "stance": จุดยืนใหม่ -1..1, '
                f'"sentiment": โทนอารมณ์ -1..1{want_hint}}}'
            )
            try:
                result = adapter.chat(
                    ModelTier.CROWD,
                    [
                        {"role": "system", "content": _persona_system(p)},
                        {"role": "user", "content": user},
                    ],
                    max_tokens=260,
                    temperature=0.7,
                    seed=seed + r * 1000 + idx,  # best-effort pin ต่อ (round, agent)
                    reasoning=False,
                )
                content, stance, sentiment, want = _parse_post(result.text)
                return DebatePost(
                    r, idx, p.segment_name, content, stance, sentiment, want_to_know=want
                )
            except Exception as exc:
                # fail-closed: ติดธง ไม่ปนใน metrics — จุดยืนเดิมคงไว้
                return DebatePost(
                    r,
                    idx,
                    p.segment_name,
                    "",
                    stances[idx],
                    0.0,
                    failed=True,
                    failure_reason=_failure_reason(exc),
                )

        with ThreadPoolExecutor(max_workers=8) as pool_ex:
            round_posts = list(pool_ex.map(ask, range(len(personas))))
        for post in round_posts:
            if not post.failed:
                stances[post.agent_idx] = post.stance
        all_posts.extend(round_posts)
        # query intent (P7-M3): รวบสิ่งที่ agent อยากรู้ → โต๊ะข่าวค้นให้ก่อนรอบถัดไป
        if news_fetcher and r < rounds - 1:
            from simulation.newsdesk import dedupe_intents

            intents = dedupe_intents([p.want_to_know for p in round_posts if p.want_to_know])
            if intents:
                try:
                    fresh = news_fetcher(intents)  # โต๊ะข่าว: gather+PII+snapshot+diet ภายใน
                    for seg, lines in (fresh or {}).items():
                        news[seg] = tuple(lines)[:6]
                except Exception:
                    pass  # ค้นไม่ได้ = รอบถัดไปใช้ข่าวชุดเดิม (degrade ไม่พัง)
        if on_round:
            on_round(r, round_posts)

    metrics = _compute_metrics(all_posts, rounds, len(personas))
    protocol = analyze_protocol(all_posts, subject=subject, rounds=rounds)
    if metrics["posts_ok"] == 0:
        failures = protocol["failure_taxonomy"]
        summary = ", ".join(f"{reason}={count}" for reason, count in sorted(failures.items()))
        raise DebateUnavailableError(
            f"debate ใช้งานไม่ได้: agent LLM ล้มเหลวทุกคำตอบ ({summary or 'unknown'})"
        )

    ok_last = [p for p in all_posts if not p.failed and p.round_no == rounds - 1]
    digest = "\n".join(f"- [{p.segment}] จุดยืน {p.stance:+.2f}: {p.content}" for p in ok_last)
    try:
        result = adapter.chat(
            ModelTier.ANALYST,
            [
                {
                    "role": "system",
                    "content": "คุณคือนักวิเคราะห์ สรุปผลดีเบตจำลอง ตอบภาษาไทยเท่านั้น ตอบ JSON ล้วน",
                },
                {
                    "role": "user",
                    "content": f"หัวข้อ: {subject}\nรอบดีเบต: {rounds}\n\n"
                    f"จุดยืนสุดท้ายของ agents:\n{digest}\n\n"
                    'ตอบ JSON: {"summary": "2-3 ประโยค", "confidence": 0..1, '
                    '"distribution": [{"bucket": "ชื่อกลุ่มความเห็น", "pct": %}], '
                    '"key_drivers": ["ปัจจัย 3-5 ข้อ"], "risks": ["ความเสี่ยง 2-4 ข้อ"]}',
                },
            ],
            max_tokens=900,
            temperature=0,
            seed=seed,
        )
        clean = re.sub(
            r"^```(?:json)?|```$", "", sanitize_llm_text(result.text).strip(), flags=re.MULTILINE
        )
        synthesis = json.loads(clean.strip())
        synthesis["confidence"] = max(0.0, min(1.0, float(synthesis.get("confidence", 0.5))))
        synthesis["fallback"] = False
    except Exception:
        synthesis = _mechanical_synthesis(all_posts, subject, rounds)

    # ความมั่นใจถูกลดตามสัดส่วน agent ที่พัง (คำตอบหายไป = ความไม่แน่นอนเพิ่ม)
    failed = metrics["posts_failed"]
    total = len(all_posts) or 1
    synthesis["confidence"] = round(synthesis["confidence"] * (1 - failed / total), 2)

    spent_after = adapter._guard.spent_usd if hasattr(adapter, "_guard") else 0.0
    return DebateResult(
        posts=tuple(all_posts),
        synthesis=synthesis,
        metrics={**metrics, "protocol_version": 1},
        protocol=protocol,
        failed_posts=failed,
        cost_usd=round(spent_after - spent_before, 6),
    )
