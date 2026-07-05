"""Executive Dashboard (DASH-01..04) — ประกอบชิ้นส่วน Trust Layer เป็นรายงานผู้บริหาร

- DASH-01 Executive Brief ≤ 3 บรรทัด (โอกาส/ความเสี่ยงสูงสุด) — **ต้องมี fragility + confidence เสมอ
  ห้ามตัวเลขเดี่ยวไร้ช่วง** (AC ของ DASH-01)
- DASH-02 Risk Heatmap รายกลุ่ม (ต่อยอด Red Team likelihood × damage)
- DASH-03 Scenario Comparison (ต่อยอด what-if fork)
- DASH-04 Synthetic Voices (ต่อยอด voice layer) + voice/population share

รายงานตัว dashboard ถูก serialize เป็น dict — layer HTML/REST ห่ออีกที (api/app.py)
คำนวณล้วน ไม่เรียก LLM เอง (รับผลที่คำนวณมาแล้วจาก simulation/redteam/voice)
"""

from dataclasses import dataclass, field

from simulation.redteam import ScoredAttack
from trust.universe import FragilityReport


@dataclass(frozen=True)
class BriefLine:
    kind: str  # "opportunity" | "risk"
    text: str


@dataclass(frozen=True)
class ExecutiveBrief:
    lines: tuple[BriefLine, ...]  # ≤ 3
    fragility_index: int
    confidence_label: str
    headline_range: tuple[float, float]  # ช่วงเสมอ ไม่ใช่ตัวเลขเดี่ยว

    def __post_init__(self):
        if len(self.lines) > 3:
            raise ValueError("Executive Brief ต้อง ≤ 3 บรรทัด (DASH-01)")


def build_executive_brief(
    *,
    delta_ci: tuple[float, float],
    fragility: FragilityReport,
    top_risk: ScoredAttack | None,
    subject: str,
) -> ExecutiveBrief:
    lo, hi = delta_ci
    lines = [
        BriefLine(
            "opportunity",
            f"{subject}: มาตรการสื่อสารมีแนวโน้มเปลี่ยนความเชื่อกลุ่มเป้าหมาย "
            f"ในช่วง [{lo:+.0%}, {hi:+.0%}] (ข้อสรุปหลัก: {fragility.majority_conclusion})",
        )
    ]
    if top_risk is not None:
        lines.append(
            BriefLine(
                "risk",
                f"ความเสี่ยงสูงสุด (risk {top_risk.risk}/25): {top_risk.attack.role_name} — "
                f"{top_risk.attack.attack[:80]}",
            )
        )
    lines.append(
        BriefLine(
            "risk" if fragility.downgraded else "opportunity",
            f"ความมั่นคงของข้อสรุป: Fragility {fragility.fragility_index}/100 "
            f"({fragility.confidence_label})",
        )
    )
    return ExecutiveBrief(
        lines=tuple(lines[:3]),
        fragility_index=fragility.fragility_index,
        confidence_label=fragility.confidence_label,
        headline_range=delta_ci,
    )


@dataclass(frozen=True)
class HeatCell:
    segment_or_role: str
    likelihood: int
    damage: int

    @property
    def risk(self) -> int:
        return self.likelihood * self.damage

    @property
    def band(self) -> str:
        r = self.risk
        return "สูง" if r >= 15 else ("กลาง" if r >= 6 else "ต่ำ")


def build_risk_heatmap(scored: list[ScoredAttack]) -> list[HeatCell]:
    """DASH-02 — รวมความเสี่ยงรายบทบาท (เอา max risk ต่อบทบาท)"""
    by_role: dict[str, ScoredAttack] = {}
    for s in scored:
        cur = by_role.get(s.attack.role_name)
        if cur is None or s.risk > cur.risk:
            by_role[s.attack.role_name] = s
    return sorted(
        (HeatCell(name, s.likelihood, s.damage) for name, s in by_role.items()),
        key=lambda c: -c.risk,
    )


@dataclass(frozen=True)
class ScenarioColumn:
    name: str
    belief_by_segment: dict[str, float]


@dataclass(frozen=True)
class Dashboard:
    subject: str
    brief: ExecutiveBrief
    heatmap: tuple[HeatCell, ...]
    scenarios: tuple[ScenarioColumn, ...]  # DASH-03 baseline vs variant
    voices: tuple[dict, ...] = field(default_factory=tuple)  # DASH-04 ตัวอย่างเสียงจริง
    voice_population_share: tuple[dict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "brief": {
                "lines": [{"kind": ln.kind, "text": ln.text} for ln in self.brief.lines],
                "fragility_index": self.brief.fragility_index,
                "confidence_label": self.brief.confidence_label,
                "headline_range": list(self.brief.headline_range),
            },
            "heatmap": [
                {"name": c.segment_or_role, "risk": c.risk, "band": c.band} for c in self.heatmap
            ],
            "scenarios": [
                {"name": s.name, "belief_by_segment": s.belief_by_segment} for s in self.scenarios
            ],
            "voices": list(self.voices),
            "voice_population_share": list(self.voice_population_share),
        }
