"""Debate engine (P6-M1) — agent LLM โพสต์โต้กันเป็นรอบ (แนวคิด GraphRAG Swarm ของ SwarmSight)

จุดที่เข้มกว่าต้นแบบ (ตามกติกา PHASE6-BRIEF):
- **seeded ทุกจุดสุ่ม**: การ sample โพสต์รอบก่อนใช้ Random(seed) เดียว draw ตามลำดับ
  ใน main thread ก่อน dispatch — run เดิม seed เดิม = feed เดิม (ตัว LLM pin seed แบบ
  best-effort ผ่าน OpenRouter — ข้อจำกัดเดียวกับ extraction, snapshot จริงคือ posts ที่เก็บ)
- **fail-closed**: parse พัง/call พัง = โพสต์ติดธง failed — ไม่ปนใน metrics/synthesis
  (ต้นแบบนับ stance 0 ต่อเงียบๆ = silent corruption)
- ทุก call ผ่าน adapter + BudgetGuard, ประเมิน cost ก่อนเริ่ม; crowd ใช้ reasoning=False
  (บทเรียน 6 ก.ค. — เร็ว 29x); production synthesis ใช้ analyst และ fail หาก analyst ล้ม
  ส่วน mechanical synthesis ใช้เฉพาะคำสั่ง rebuild stored snapshot ที่ผู้ใช้เรียกชัดเจน
- ภาษาไทย first-class + กติกา prompt มาตรฐาน (ห้ามกุชื่อ/ตัวเลข)
"""

import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from random import Random
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from core.config import get_settings
from core.llm.adapter import LLMAdapter, ModelTier
from core.llm.cost import BudgetGuard, CostEstimator, TierLoad
from core.text import sanitize_llm_text
from simulation.debate_protocol import (
    MoveType,
    compact_verifier_report,
    normalize_evidence_refs,
    normalize_move_type,
    verify_moves,
)
from simulation.persona import Persona
from simulation.tipping import detect_tipping_points

DEFAULT_ROUNDS = 3
REPLY_SAMPLE = 6
MAX_POST_CHARS = 400

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "stance": {"type": "number", "minimum": -1, "maximum": 1},
        "sentiment": {"type": "number", "minimum": -1, "maximum": 1},
        "want_to_know": {"type": "string"},
        "move_type": {
            "type": "string",
            "enum": ["claim", "evidence", "counterclaim", "concession", "question"],
        },
        "reply_to": {"type": "string"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": [
        "content",
        "stance",
        "sentiment",
        "want_to_know",
        "move_type",
        "reply_to",
        "evidence_refs",
    ],
    "additionalProperties": False,
}

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _SynthesisDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: NonEmptyText
    pct: float = Field(ge=0, le=100)


class _SynthesisJudge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Annotated[str, Field(pattern="^(pass|warn|fail)$")]
    citation_assessment: NonEmptyText
    contradiction_assessment: NonEmptyText
    schema_assessment: NonEmptyText
    unsupported_claims: list[str]
    notes: list[str]


class _SynthesisContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: NonEmptyText
    confidence: float = Field(ge=0, le=1)
    distribution: list[_SynthesisDistribution] = Field(min_length=1)
    key_drivers: list[NonEmptyText] = Field(min_length=1)
    risks: list[NonEmptyText] = Field(min_length=1)
    judge: _SynthesisJudge


SYNTHESIS_SCHEMA = _SynthesisContract.model_json_schema()

# วัดจริง 18 ก.ค. 2026 (run a00d908f): synthesis ไทยครบ contract ที่ 40 agents ใช้เกิน 900 tokens
# ทั้งสอง attempt โดนตัดที่เพดานพอดี (output = max_tokens, finish_reason=length) → run fail ทั้งที่
# โพสต์สำเร็จ 120/120 — เพดานต้องเผื่อพอ และ retry ต้องได้เพดานสูงกว่าเดิม
# ค่านี้เป็น default; ผู้ใช้ทับได้จากหน้า Settings (llm_synthesis_max_tokens — มติผู้ใช้ 18 ก.ค.)
ANALYST_SYNTHESIS_MAX_TOKENS = 2000


def synthesis_retry_ceiling(base_tokens: int) -> int:
    """เพดานของ bounded retry — สูงกว่ารอบแรกเสมอเผื่อกรณีคำตอบถูกตัด"""
    return max(base_tokens + 500, int(base_tokens * 1.5))


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
    parser_mode: str = ""
    move_id: str = ""
    move_type: str = MoveType.CLAIM
    parent_move_id: str = ""
    evidence_refs: tuple[str, ...] = ()
    # TRUST-07 ในดีเบต (ADR-0022): expressed=False = agent คิด/อัปเดตจุดยืนแต่ไม่โพสต์
    # (silent majority) — โพสต์เงียบไม่เข้าฟีดคนอื่น; วัด voice share vs population share ได้
    expressed: bool = True

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
            "parser_mode": self.parser_mode,
            "move_id": self.move_id,
            "move_type": str(self.move_type),
            "expressed": self.expressed,
            "parent_move_id": self.parent_move_id,
            "evidence_refs": list(self.evidence_refs),
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


def make_debate_adapter(
    agents: int,
    rounds: int,
    *,
    monthly_reservation_id: str = "",
) -> LLMAdapter:
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
    synthesis_tokens = int(settings.llm_synthesis_max_tokens or ANALYST_SYNTHESIS_MAX_TOKENS)
    loads = [
        TierLoad(settings.llm_model_crowd, agents * rounds, 900, 160),
        # Reserve one bounded contract-repair retry for the Executive Readout.
        # Input จริงโตตาม digest รอบสุดท้าย (วัดจริง ~7,000 tokens ที่ 40 agents) และ output
        # ต้องเผื่อถึงเพดาน retry — ประเมินต่ำกว่าจริงทำให้ BudgetGuard เช็คงบไม่ตรงความเป็นจริง
        TierLoad(
            settings.llm_model_analyst,
            2,
            9_000,
            synthesis_retry_ceiling(synthesis_tokens),
        ),
    ]
    estimate = CostEstimator(pricing).estimate(loads)
    # งบรวมเดือน (P6-M5) ก่อน — ยอดสะสม + estimate เกิน = block
    check_monthly_budget(
        settings.postgres_url,
        estimate.total_usd,
        effective_monthly_cap(),
        reservation_id=monthly_reservation_id,
    )
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    guard.check_estimate(estimate)  # งบต่อรัน
    return LLMAdapter(
        settings,
        pricing,
        guard,
        monthly_cap_usd=effective_monthly_cap(),
        monthly_reservation_id=monthly_reservation_id,
    )


def _initial_stance(p: Persona) -> float:
    # Red Team ใน debate: จุดยืนตั้งต้นแบบ SwarmSight (contrarian −0.6, auditor −0.3)
    if "contrarian" in p.traits:
        return -0.6
    if "auditor" in p.traits:
        return -0.3
    return 0.0


def _persona_system(p: Persona) -> str:
    # Red Team แบบ devil's advocate เต็มรูป (ADR-0022) — งานวิจัยพบว่า "soft framing"
    # (แค่บอกบทบาทเบาๆ) ไม่ต่างจาก baseline; ต้องสั่งโจมตีข้อสรุปเสียงข้างมากอย่างเป็นระบบ
    # และห้ามคล้อยตาม ถึงจะ induce disagreement ได้จริง (IUI'24 devil's advocate;
    # OpenReview mxBmj5LYU2 "Only the Devil's Advocate Works")
    role = ""
    if "contrarian" in p.traits:
        role = (
            " บทบาทของคุณ: devil's advocate ประจำวง — อ่านโพสต์ทั้งหมดแล้วระบุข้อสรุปที่"
            "เสียงข้างมากกำลังเห็นพ้อง จากนั้นโจมตีข้อสรุปนั้นด้วยข้อโต้แย้งที่แรงและมีเหตุผลที่สุด"
            " ห้ามคล้อยตามเสียงข้างมาก ห้ามยอมแพ้ ห้ามใช้ move 'concession'"
            " และจุดยืนของคุณต้องไม่เป็นบวก"
        )
    elif "auditor" in p.traits:
        role = (
            " บทบาทของคุณ: ผู้ตรวจสอบหลักฐาน — ไล่ชี้ claim ในวงที่ไม่มีหลักฐานอ้างอิง"
            " ตั้งคำถามบังคับให้ผู้โพสต์แสดง evidence อย่ายอมรับข้อสรุปที่ยังไม่มีหลักฐานรองรับ"
            " ใช้ move 'question' หรือ 'counterclaim' เป็นหลัก"
        )
    elif "redteam" in p.traits:
        role = " บทบาทพิเศษของคุณ: ตั้งคำถามกับฉันทามติที่กำลังก่อตัว หาจุดอ่อนของข้อสรุป"
    return (
        f"คุณคือคนไทยกลุ่ม '{p.segment_name}' "
        f"(เกรงใจ {p.kreng_jai:.1f}, ช่องว่างพูด-ทำ {p.say_do_gap:.1f}, "
        f"ใช้มีม/ประชด {p.sarcasm_meme:.1f}) "
        f"ลักษณะ: {', '.join(p.traits) or 'ไม่ระบุ'}.{role} "
        "ตอบภาษาไทยเท่านั้น ห้ามกุชื่อ/ตัวเลข — จำไม่ได้ให้บอกว่าไม่แน่ใจ เรียกคนด้วยบทบาท "
        "ตอบเป็น JSON ล้วนเท่านั้น (ไม่มี markdown)"
    )


def _feed_weight(reader: Persona, author: Persona) -> float:
    """น้ำหนักที่ผู้อ่านจะเห็นโพสต์ของผู้เขียน — selective exposure ตาม media diet (ADR-0022)

    ใช้ overlap ของ channel_mix (อยู่ช่องทางเดียวกัน = เจอกันบ่อย) + ฐาน 0.25 กัน echo
    chamber สมบูรณ์ (ยังมีโอกาสเห็นข้ามกลุ่มเสมอ) — แทน uniform sampling เดิมที่ทุกคน
    เห็นทุกคนเท่ากัน ซึ่งขัดกับ media diet ที่ Fabric/News Desk ทำแล้ว
    """
    channels = set(reader.channel_mix) | set(author.channel_mix)
    overlap = sum(
        min(reader.channel_mix.get(c, 0.0), author.channel_mix.get(c, 0.0)) for c in channels
    )
    return 0.25 + 0.75 * overlap


def _weighted_sample(rng: Random, pool: list, weights: list[float], k: int) -> list:
    """weighted sampling without replacement — deterministic ตามลำดับ draw ของ rng"""
    pool = list(pool)
    weights = list(weights)
    chosen = []
    for _ in range(min(k, len(pool))):
        total = sum(weights)
        if total <= 0:
            break
        r = rng.random() * total
        acc = 0.0
        pick = len(pool) - 1
        for i, w in enumerate(weights):
            acc += w
            if r <= acc:
                pick = i
                break
        chosen.append(pool.pop(pick))
        weights.pop(pick)
    return chosen


def _parse_post(text: str) -> tuple[str, float, float, str]:
    data = _load_json_object(text)
    content = str(data["content"]).strip()[:MAX_POST_CHARS]
    if not content:
        raise ValueError("content ว่าง")
    stance = max(-1.0, min(1.0, float(data["stance"])))
    sentiment = max(-1.0, min(1.0, float(data.get("sentiment", 0))))
    want = str(data.get("want_to_know", "")).strip()[:120]
    return content, stance, sentiment, want


def _parse_move_metadata(text: str) -> tuple[str, str, tuple[str, ...]]:
    data = _load_json_object(text)
    return (
        normalize_move_type(data.get("move_type")),
        str(data.get("reply_to", "")).strip()[:80],
        normalize_evidence_refs(data.get("evidence_refs")),
    )


def _load_json_object(text: str) -> dict:
    """Parse one JSON object while tolerating prose or Markdown around it.

    Providers occasionally wrap an otherwise valid response despite a JSON-only prompt.
    We only accept an object decoded by the standard parser; malformed JSON still fails closed.
    """
    clean = sanitize_llm_text(text).strip()
    try:
        value = json.loads(clean)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        for start, char in enumerate(clean):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(clean[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        raise original_error
    if not isinstance(value, dict):
        raise TypeError("LLM response must be a JSON object")
    return value


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
    per_round_dispersion: list[float] = []
    for r in range(rounds):
        rs = [p.stance for p in ok if p.round_no == r]
        per_round_avg.append(sum(rs) / len(rs) if rs else 0.0)
        per_round_dispersion.append(statistics.pstdev(rs) if len(rs) > 1 else 0.0)
    last = [p.stance for p in ok if p.round_no == rounds - 1]
    dispersion = statistics.pstdev(last) if len(last) > 1 else 0.0
    # tipping: map stance [-1,1] → [0,1] แล้วใช้ detector เดิม (threshold 0.15 ของ share
    # = 0.30 บนสเกล stance — สอดคล้อง SwarmSight ที่ใช้ 0.25)
    series = [(s + 1) / 2 for s in per_round_avg]
    tipping = [tp.to_dict() for tp in detect_tipping_points(series)] if len(series) > 1 else []
    metrics = {
        "per_round_avg_stance": [round(s, 4) for s in per_round_avg],
        "final_dispersion": round(dispersion, 4),
        "tipping_points": tipping,
        "posts_ok": len(ok),
        "posts_failed": len(posts) - len(ok),
        "agent_count": agent_count,
        "parser_fallback_posts": sum(
            1 for p in ok if p.parser_mode == "parser_fallback_unsupported"
        ),
    }
    metrics.update(_conformity_metrics(ok, rounds, per_round_avg, per_round_dispersion))
    metrics.update(_voice_metrics(ok, rounds))
    red_team = _red_team_pressure(ok)
    if red_team:
        metrics["red_team_pressure"] = red_team
    return metrics


def _conformity_metrics(
    ok: list[DebatePost],
    rounds: int,
    per_round_avg: list[float],
    per_round_dispersion: list[float],
) -> dict:
    """วัดความเสี่ยง "ฉันทามติปลอม" (ADR-0022) — วงดีเบต LLM มีแนวโน้ม sycophancy/conformity
    สูงจนหุบเข้า consensus เร็วผิดจริง (arXiv:2509.23055, 2604.02668) และการพลิกจุดยืน
    ต้องแยก "คล้อยตามเสียงข้างมาก" ออกจาก "ถูกโน้มน้าวด้วยหลักฐาน" (arXiv:2606.00820)

    ใช้ค่าเฉลี่ยรอบก่อนหน้าเป็น proxy ของเสียงข้างมากที่ agent เห็น (ฟีดคือ sample ของรอบก่อน)
    """
    convergence_rate = (
        (per_round_dispersion[-1] - per_round_dispersion[0]) / max(1, rounds - 1)
        if rounds > 1
        else 0.0
    )
    prev_stance: dict[int, float] = {}
    flips_total = 0
    flips_conforming = 0
    flips_evidenced = 0
    moved_toward_majority = 0
    movable = 0
    for r in range(rounds):
        majority = per_round_avg[r - 1] if r > 0 else 0.0
        for p in sorted((q for q in ok if q.round_no == r), key=lambda q: q.agent_idx):
            before = prev_stance.get(p.agent_idx)
            if r > 0 and before is not None:
                movable += 1
                if abs(p.stance - majority) < abs(before - majority) - 1e-9:
                    moved_toward_majority += 1
                flipped = before * p.stance < 0 and abs(p.stance - before) >= 0.4
                if flipped:
                    flips_total += 1
                    if p.evidence_refs or p.move_type in {
                        MoveType.EVIDENCE,
                        MoveType.COUNTERCLAIM,
                    }:
                        flips_evidenced += 1
                    elif abs(p.stance - majority) < abs(before - majority):
                        flips_conforming += 1
            prev_stance[p.agent_idx] = p.stance
    final_dispersion = per_round_dispersion[-1] if per_round_dispersion else 0.0
    return {
        "per_round_dispersion": [round(d, 4) for d in per_round_dispersion],
        "convergence_rate": round(convergence_rate, 4),
        "majority_alignment": round(moved_toward_majority / movable, 4) if movable else None,
        "stance_flips": {
            "total": flips_total,
            "conforming_without_evidence": flips_conforming,
            "evidenced_or_argued": flips_evidenced,
        },
        # ธงเตือน: วงหุบเข้าฉันทามติเร็วและแคบ — ต้องอ่านผลอย่างระวัง (Honesty over impressiveness)
        "consensus_warning": bool(final_dispersion < 0.15 and convergence_rate <= -0.1),
    }


def _voice_metrics(ok: list[DebatePost], rounds: int) -> dict:
    """voice share vs population share ในดีเบต (TRUST-07) — เสียงที่ปรากฏ ≠ ความเห็นประชากร"""
    if not ok:
        return {}
    expressed = [p for p in ok if p.expressed]
    last_all = [p.stance for p in ok if p.round_no == rounds - 1]
    last_expressed = [p.stance for p in ok if p.round_no == rounds - 1 and p.expressed]
    gap = (
        (sum(last_expressed) / len(last_expressed)) - (sum(last_all) / len(last_all))
        if last_expressed and last_all
        else 0.0
    )
    return {
        "voice_share": round(len(expressed) / len(ok), 4),
        # บวก = เสียงที่ปรากฏเอนไปทางเห็นด้วยมากกว่าความเห็นจริงของประชากร (say-do gap ระดับวง)
        "voice_population_stance_gap": round(gap, 4),
    }


def _red_team_pressure(ok: list[DebatePost]) -> dict | None:
    """วัดว่า red team สร้างแรงเสียดทานจริงแค่ไหน — คำนวณได้จากโพสต์ที่เก็บ (retroactive)"""
    from simulation.redteam_population import RED_TEAM_SEGMENT

    red_posts = [p for p in ok if p.segment == RED_TEAM_SEGMENT]
    if not red_posts:
        return None
    red_move_ids = {p.move_id for p in red_posts}
    others = [p for p in ok if p.segment != RED_TEAM_SEGMENT]
    replies = [p for p in others if p.parent_move_id in red_move_ids]
    return {
        "red_posts": len(red_posts),
        "red_avg_stance": round(sum(p.stance for p in red_posts) / len(red_posts), 4),
        "replies_from_others": len(replies),
        "counterclaims_from_others": sum(
            1 for p in replies if p.move_type == MoveType.COUNTERCLAIM
        ),
        "engagement_rate": round(len(replies) / max(1, len(others)), 4),
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
            parser_mode=str(p.get("parser_mode", "")),
            move_id=str(p.get("move_id", "")),
            move_type=normalize_move_type(p.get("move_type")),
            parent_move_id=str(p.get("parent_move_id", "")),
            evidence_refs=normalize_evidence_refs(p.get("evidence_refs", [])),
            # posts จาก DB ไม่มี expressed (คอลัมน์คงที่) → default True; voice metrics
            # ที่แม่นอยู่ใน payload ของ run จริงเท่านั้น
            expressed=bool(p.get("expressed", True)),
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
    protocol["verifier"] = verify_moves(debate_posts)
    return {"synthesis": synthesis, "metrics": metrics, "protocol": protocol}


def run_debate(
    personas: list[Persona],
    *,
    subject: str,
    rounds: int = DEFAULT_ROUNDS,
    seed: int,
    adapter: LLMAdapter,
    context_chunks: tuple[str, ...] = (),
    evidence_ids: tuple[str, ...] = (),
    segment_news: dict[str, tuple[str, ...]] | None = None,
    news_fetcher=None,  # callable(list[str]) -> dict[segment, tuple[str,...]] — โต๊ะข่าวค้นตาม intent
    on_round=None,
    synthesis_max_tokens: int | None = None,  # None/0 = ใช้ default; ผู้ใช้ตั้งจากหน้า Settings
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
        "\n".join(
            f"[{evidence_ids[i] if i < len(evidence_ids) else f'E{i + 1}'}] {c[:600]}"
            for i, c in enumerate(context_chunks[:6])
        )
        if context_chunks
        else "(ไม่มีเอกสารอ้างอิง — ใช้มุมมองของกลุ่มคุณ)"
    )
    spent_before = adapter._guard.spent_usd if hasattr(adapter, "_guard") else 0.0

    for r in range(rounds):
        # ฟีดเห็นเฉพาะโพสต์ที่ "แสดงออก" (TRUST-07 — โพสต์เงียบมีจุดยืนแต่ไม่มีเสียง)
        prev = [p for p in all_posts if p.round_no == r - 1 and not p.failed and p.expressed]
        prev_mean = sum(p.stance for p in prev) / len(prev) if prev else 0.0
        # voice draw ต่อ agent ใน main thread (deterministic) — red team เสียงดังเสมอ
        expressed_flags = [
            ("redteam" in personas[idx].traits) or rng.random() < personas[idx].voice_activity
            for idx in range(len(personas))
        ]
        # sample feed ต่อ agent แบบ deterministic — draw ทั้งหมดใน main thread ตามลำดับ agent
        feeds: list[str] = []
        for idx in range(len(personas)):
            pool = [p for p in prev if p.agent_idx != idx]
            if "redteam" in personas[idx].traits:
                # devil's advocate เห็นโพสต์ที่ align กับเสียงข้างมากที่สุด — มีเป้าโจมตีชัด
                chosen = sorted(pool, key=lambda p: (abs(p.stance - prev_mean), p.agent_idx))[
                    :REPLY_SAMPLE
                ]
            elif len(pool) <= REPLY_SAMPLE:
                chosen = pool
            else:
                # selective exposure (ADR-0022): น้ำหนักตาม overlap ของ media diet
                weights = [_feed_weight(personas[idx], personas[p.agent_idx]) for p in pool]
                chosen = _weighted_sample(rng, pool, weights, REPLY_SAMPLE)
            feeds.append(
                "\n".join(
                    f"- [{p.move_id} | {p.segment} | {p.move_type} | จุดยืน {p.stance:+.2f}]: "
                    f"{p.content}"
                    for p in chosen
                )
                or "(ยังไม่มีโพสต์ก่อนหน้า — นี่คือรอบเปิด แสดงมุมมองตั้งต้นของคุณ)"
            )

        # ฟีดข่าวของกลุ่ม (media diet — P7): แต่ละ segment เห็นชุดข่าวไม่เหมือนกัน
        news_snapshot = dict(news)  # freeze ต่อรอบ ให้ทุก thread เห็นชุดเดียวกัน

        def ask(
            idx: int,
            r: int = r,
            feeds: list[str] = feeds,
            news_now: dict = news_snapshot,
            expressed_flags: list[bool] = expressed_flags,
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
                f"โพสต์ล่าสุดจากคนอื่น (รอบ {r + 1}):\n{feeds[idx]}\n"
                "เขียนโพสต์ 1 โพสต์ (ไม่เกิน 60 คำ) ตามเสียงของกลุ่มคุณ — โต้ตอบประเด็น/โพสต์อื่นได้\n"
                'ตอบ JSON: {"content": "ข้อความโพสต์", "stance": จุดยืนใหม่ -1..1, '
                f'"sentiment": โทนอารมณ์ -1..1{want_hint}, '
                '"move_type": "claim|evidence|counterclaim|concession|question", '
                '"reply_to": "move ID ก่อนหน้า หรือเว้นว่าง", '
                '"evidence_refs": ["evidence ID เช่น E1"]}'
            )
            try:
                structured_kwargs = (
                    {"response_schema": POST_SCHEMA, "schema_name": "debate_post"}
                    if getattr(adapter, "supports_structured_outputs", lambda: False)()
                    else {}
                )
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
                    **structured_kwargs,
                )
                content, stance, sentiment, want = _parse_post(result.text)
                move_type, parent_move_id, refs = _parse_move_metadata(result.text)
                if "contrarian" in p.traits:
                    # persistent dissent (ADR-0022): devil's advocate ห้ามลอยตามเสียงข้างมาก
                    # — จุดยืนไม่เป็นบวก และไม่ยอมแพ้ (concession → counterclaim)
                    stance = min(stance, 0.0)
                    if move_type == MoveType.CONCESSION:
                        move_type = MoveType.COUNTERCLAIM
                return DebatePost(
                    r,
                    idx,
                    p.segment_name,
                    content,
                    stance,
                    sentiment,
                    want_to_know=want,
                    parser_mode=getattr(result, "structured_mode", "parser_fallback_capability"),
                    move_id=f"m-r{r + 1}-a{idx + 1}",
                    move_type=move_type,
                    parent_move_id=parent_move_id,
                    evidence_refs=refs,
                    expressed=expressed_flags[idx],
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
                    parser_mode="failed",
                    move_id=f"m-r{r + 1}-a{idx + 1}",
                    move_type=MoveType.CLAIM,
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
    verifier = verify_moves(all_posts, evidence_ids=set(evidence_ids))
    protocol["verifier"] = verifier
    protocol["move_lineage"] = verifier["lineage"]
    if metrics["posts_ok"] == 0:
        failures = protocol["failure_taxonomy"]
        summary = ", ".join(f"{reason}={count}" for reason, count in sorted(failures.items()))
        raise DebateUnavailableError(
            f"debate ใช้งานไม่ได้: agent LLM ล้มเหลวทุกคำตอบ ({summary or 'unknown'})"
        )

    ok_last = [p for p in all_posts if not p.failed and p.round_no == rounds - 1]
    digest = "\n".join(f"- [{p.segment}] จุดยืน {p.stance:+.2f}: {p.content}" for p in ok_last)
    verifier_digest = json.dumps(
        compact_verifier_report(verifier), ensure_ascii=False, separators=(",", ":")
    )
    analyst_attempts = 0
    result = None
    try:
        structured_kwargs = (
            {"response_schema": SYNTHESIS_SCHEMA, "schema_name": "debate_synthesis"}
            if getattr(adapter, "supports_structured_outputs", lambda: False)()
            else {}
        )
        analyst_messages = [
            {
                "role": "system",
                "content": (
                    "คุณคือนักวิเคราะห์และ judge สรุปผลดีเบตจำลอง ตอบภาษาไทยเท่านั้น "
                    "ตอบ JSON ล้วน ห้ามลดทอนข้อผิดพลาดที่ deterministic verifier รายงาน"
                ),
            },
            {
                "role": "user",
                "content": f"หัวข้อ: {subject}\nรอบดีเบต: {rounds}\n\n"
                f"จุดยืนสุดท้ายของ agents:\n{digest}\n\n"
                f"รายงาน verifier:\n{verifier_digest}\n\n"
                'ตอบ JSON: {"summary": "2-3 ประโยค", "confidence": 0..1, '
                '"distribution": [{"bucket": "ชื่อกลุ่มความเห็น", "pct": %}], '
                '"key_drivers": ["ปัจจัย 3-5 ข้อ"], "risks": ["ความเสี่ยง 2-4 ข้อ"], '
                '"judge": {"verdict": "pass|warn|fail", '
                '"citation_assessment": "...", "contradiction_assessment": "...", '
                '"schema_assessment": "...", '
                '"unsupported_claims": ["..."], "notes": ["..."]}}',
            },
        ]
        base_max_tokens = int(synthesis_max_tokens or 0) or ANALYST_SYNTHESIS_MAX_TOKENS
        analyst_attempts = 1
        result = adapter.chat(
            ModelTier.ANALYST,
            analyst_messages,
            max_tokens=base_max_tokens,
            temperature=0,
            seed=seed,
            **structured_kwargs,
        )
        try:
            synthesis = _SynthesisContract.model_validate(
                _load_json_object(result.text)
            ).model_dump()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Some provider/model combinations acknowledge json_schema but return a nested
            # fragment, or the response hits max_tokens and truncates mid-object. Retry once
            # without provider-side structured output and with a higher token ceiling, then
            # apply the exact same local contract. Fail-closed and BudgetGuard-metered.
            analyst_attempts = 2
            truncated = getattr(result, "finish_reason", "") == "length"
            retry_note = (
                " คำตอบก่อนหน้าถูกตัดกลางคันเพราะยาวเกิน กรุณาตอบกระชับลงและส่ง JSON ให้จบสมบูรณ์"
                if truncated
                else " คำตอบก่อนหน้าไม่ครบ contract กรุณาส่ง object หลักให้ครบทุก field"
            )
            retry_messages = [
                {
                    "role": "system",
                    "content": analyst_messages[0]["content"] + retry_note,
                },
                analyst_messages[1],
            ]
            result = adapter.chat(
                ModelTier.ANALYST,
                retry_messages,
                max_tokens=synthesis_retry_ceiling(base_max_tokens),
                temperature=0,
                seed=seed + 1,
            )
            synthesis = _SynthesisContract.model_validate(
                _load_json_object(result.text)
            ).model_dump()
        synthesis["confidence"] = max(0.0, min(1.0, float(synthesis.get("confidence", 0.5))))
        synthesis["fallback"] = False
        synthesis["analyst_attempts"] = analyst_attempts
        synthesis["parser_mode"] = (
            "contract_retry_parser"
            if analyst_attempts == 2
            else getattr(result, "structured_mode", "parser_fallback_capability")
        )
        synthesis["model_version"] = getattr(result, "model", "")
        judge = synthesis.get("judge")
        if not isinstance(judge, dict):
            synthesis["judge"] = {
                "verdict": "fail" if verifier["status"] == "fail" else "warn",
                "citation_assessment": "analyst response ไม่มี judge contract",
                "contradiction_assessment": "ใช้ deterministic verifier เท่านั้น",
                "schema_assessment": "analyst response ไม่มี judge contract",
                "unsupported_claims": [],
                "notes": ["analyst_judge_unavailable"],
            }
        else:
            verdict_rank = {"pass": 0, "warn": 1, "fail": 2}
            verifier_floor = verifier.get("status", "pass")
            analyst_rank = verdict_rank.get(judge.get("verdict"), -1)
            if verifier_floor in verdict_rank and analyst_rank < verdict_rank[verifier_floor]:
                judge["verdict"] = verifier_floor
                judge["notes"] = [*list(judge.get("notes") or []), "verifier_floor_applied"]
    except Exception as exc:
        # Production runs must not substitute a deterministic summary for a failed analyst.
        # Return the posts/metrics so the caller can persist audit evidence, then fail the run.
        failure_reason = _failure_reason(exc)
        if (
            failure_reason in {"json_parse_error", "schema_missing_field", "schema_value_error"}
            and getattr(result, "finish_reason", "") == "length"
        ):
            # คำตอบชน max_tokens แล้วขาดกลางคัน — คนละสาเหตุกับ model ส่ง schema ผิด
            failure_reason = "llm_truncated"
        synthesis = {
            "status": "analyst_failed",
            "summary": "",
            "confidence": 0.0,
            "distribution": [],
            "key_drivers": [],
            "risks": ["analyst model ไม่พร้อม; ไม่มีการสร้าง mechanical fallback"],
            "fallback": False,
            "parser_mode": "analyst_failed",
            "failure_reason": failure_reason,
            "analyst_attempts": analyst_attempts,
        }
        synthesis["judge"] = {
            "verdict": "fail",
            "citation_assessment": "analyst judge ไม่พร้อม",
            "contradiction_assessment": "analyst judge ไม่พร้อม",
            "schema_assessment": "analyst response ไม่ผ่าน contract",
            "unsupported_claims": [],
            "notes": ["run_must_fail_no_mechanical_fallback"],
        }

    protocol["analyst_judge"] = synthesis["judge"]

    # ความมั่นใจถูกลดตามสัดส่วน agent ที่พัง (คำตอบหายไป = ความไม่แน่นอนเพิ่ม)
    failed = metrics["posts_failed"]
    total = len(all_posts) or 1
    synthesis["confidence"] = round(synthesis["confidence"] * (1 - failed / total), 2)

    spent_after = adapter._guard.spent_usd if hasattr(adapter, "_guard") else 0.0
    return DebateResult(
        posts=tuple(all_posts),
        synthesis=synthesis,
        metrics={**metrics, "protocol_version": 2},
        protocol=protocol,
        failed_posts=failed,
        cost_usd=round(spent_after - spent_before, 6),
    )
