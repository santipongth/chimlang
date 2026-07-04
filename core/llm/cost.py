"""Cost estimator + budget guard (กฎ Cost guard ใน CLAUDE.md / NFR-02)

- ก่อนเริ่ม run: ประเมิน cost จาก workload spec — เกิน cap ห้ามเริ่ม
- ระหว่าง run: สะสม cost จริงจาก token usage — แตะ cap ให้ abort พร้อมยอดที่ใช้ไป
"""

from dataclasses import dataclass, field


class BudgetExceededError(RuntimeError):
    def __init__(self, *, usd: float, cap_usd: float, phase: str):
        super().__init__(
            f"งบเกินเพดาน ({phase}): {usd:.4f} USD เทียบ cap {cap_usd:.2f} USD — abort run"
        )
        self.usd = usd
        self.cap_usd = cap_usd
        self.phase = phase


@dataclass(frozen=True)
class TierLoad:
    """ปริมาณงานของ model หนึ่งตัวใน run: จำนวน call และ token เฉลี่ยต่อ call"""

    model: str
    calls: int
    avg_input_tokens: int
    avg_output_tokens: int


@dataclass(frozen=True)
class CostEstimate:
    total_usd: float
    breakdown: dict[str, float]  # model -> usd


class CostEstimator:
    def __init__(self, pricing):
        self._pricing = pricing

    def estimate(self, loads: list[TierLoad]) -> CostEstimate:
        breakdown: dict[str, float] = {}
        for load in loads:
            usd = load.calls * self._pricing.cost_usd(
                load.model, load.avg_input_tokens, load.avg_output_tokens
            )
            breakdown[load.model] = breakdown.get(load.model, 0.0) + usd
        return CostEstimate(total_usd=sum(breakdown.values()), breakdown=breakdown)


@dataclass
class BudgetGuard:
    cap_usd: float
    spent_usd: float = field(default=0.0)

    def check_estimate(self, estimate: CostEstimate) -> None:
        """เรียกก่อนเริ่ม run — estimate เกิน cap = ไม่เริ่ม"""
        if estimate.total_usd > self.cap_usd:
            raise BudgetExceededError(
                usd=estimate.total_usd, cap_usd=self.cap_usd, phase="estimate"
            )

    def add_actual(self, usd: float) -> None:
        """เรียกหลังทุก LLM call — ยอดสะสมแตะ cap = abort กลาง run"""
        self.spent_usd += usd
        if self.spent_usd >= self.cap_usd:
            raise BudgetExceededError(usd=self.spent_usd, cap_usd=self.cap_usd, phase="runtime")
