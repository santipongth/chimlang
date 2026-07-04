import pytest

from core.llm import (
    BudgetExceededError,
    BudgetGuard,
    CostEstimator,
    PricingRegistry,
    TierLoad,
    UnknownModelPricingError,
)
from tests.conftest import ANALYST_MODEL, CROWD_MODEL


def test_estimate_math_exact(pricing):
    est = CostEstimator(pricing).estimate(
        [
            # crowd: 1000 calls × (1000 in × $1/M + 200 out × $4/M) = 1000 × $0.0018 = $1.80
            TierLoad(model=CROWD_MODEL, calls=1000, avg_input_tokens=1000, avg_output_tokens=200),
            # analyst: 10 calls × (2000 in × $10/M + 1000 out × $40/M) = 10 × $0.06 = $0.60
            TierLoad(model=ANALYST_MODEL, calls=10, avg_input_tokens=2000, avg_output_tokens=1000),
        ]
    )
    assert est.breakdown[CROWD_MODEL] == pytest.approx(1.80)
    assert est.breakdown[ANALYST_MODEL] == pytest.approx(0.60)
    assert est.total_usd == pytest.approx(2.40)


def test_estimate_over_cap_aborts_before_run(pricing):
    guard = BudgetGuard(cap_usd=1.0)
    est = CostEstimator(pricing).estimate(
        [TierLoad(model=CROWD_MODEL, calls=1000, avg_input_tokens=1000, avg_output_tokens=200)]
    )
    with pytest.raises(BudgetExceededError) as exc:
        guard.check_estimate(est)
    assert exc.value.phase == "estimate"
    assert guard.spent_usd == 0.0  # ยังไม่ได้ใช้เงินจริง


def test_estimate_at_cap_is_allowed(pricing):
    guard = BudgetGuard(cap_usd=2.40)
    est = CostEstimator(pricing).estimate(
        [
            TierLoad(model=CROWD_MODEL, calls=1000, avg_input_tokens=1000, avg_output_tokens=200),
            TierLoad(model=ANALYST_MODEL, calls=10, avg_input_tokens=2000, avg_output_tokens=1000),
        ]
    )
    guard.check_estimate(est)  # เท่า cap พอดี = เริ่มได้


def test_runtime_accumulation_aborts_at_cap():
    guard = BudgetGuard(cap_usd=1.0)
    guard.add_actual(0.4)
    guard.add_actual(0.4)
    with pytest.raises(BudgetExceededError) as exc:
        guard.add_actual(0.4)
    assert exc.value.phase == "runtime"
    assert guard.spent_usd == pytest.approx(1.2)  # ยอดสะสมถูกรายงานตอน abort


def test_unknown_model_pricing_fails_closed():
    pricing = PricingRegistry({})
    with pytest.raises(UnknownModelPricingError):
        CostEstimator(pricing).estimate(
            [TierLoad(model="mystery/model", calls=1, avg_input_tokens=1, avg_output_tokens=1)]
        )


def test_pricing_yaml_in_repo_loads():
    # ไฟล์ config/pricing.yaml จริงต้อง parse ได้ และมีราคาของ model ที่เลือกใช้จริง (ADR-0001)
    registry = PricingRegistry.from_yaml()
    assert registry.cost_usd("qwen/qwen3.5-flash-02-23", 1_000_000, 0) > 0
    assert registry.cost_usd("qwen/qwen3-235b-a22b-2507", 1_000_000, 0) > 0
