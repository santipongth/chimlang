import pytest

from core.config import Settings
from core.llm import BudgetExceededError, BudgetGuard, LLMAdapter, ModelTier
from core.llm.adapter import AdapterConfigError
from tests.conftest import ANALYST_MODEL, CROWD_MODEL


def make_adapter(settings, pricing, fake_client, cap_usd=5.0):
    return LLMAdapter(settings, pricing, BudgetGuard(cap_usd=cap_usd), client=fake_client)


def test_tier_routing_uses_configured_models(settings, pricing, fake_client, fake_completions):
    adapter = make_adapter(settings, pricing, fake_client)

    adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "สวัสดี"}])
    adapter.chat(ModelTier.ANALYST, [{"role": "user", "content": "วิเคราะห์"}])

    assert fake_completions.calls[0]["model"] == CROWD_MODEL
    assert fake_completions.calls[1]["model"] == ANALYST_MODEL


def test_result_carries_usage_and_cost(settings, pricing, fake_client):
    adapter = make_adapter(settings, pricing, fake_client)
    result = adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "สวัสดี"}])

    assert result.text == "สวัสดีครับ"
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    # 100×$1/M + 20×$4/M = $0.00018
    assert result.cost_usd == pytest.approx(0.00018)


def test_seed_and_temperature_forwarded_only_when_set(
    settings, pricing, fake_client, fake_completions
):
    adapter = make_adapter(settings, pricing, fake_client)

    adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "ก"}])
    assert "seed" not in fake_completions.calls[0]
    assert "temperature" not in fake_completions.calls[0]

    adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "ข"}], seed=42, temperature=0.7)
    assert fake_completions.calls[1]["seed"] == 42
    assert fake_completions.calls[1]["temperature"] == 0.7


def test_reasoning_flag_forwarded_only_when_set(settings, pricing, fake_client, fake_completions):
    adapter = make_adapter(settings, pricing, fake_client)

    adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "ก"}])
    assert "extra_body" not in fake_completions.calls[0]  # default = พฤติกรรมเดิม (คิดลึกได้)

    adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "ข"}], reasoning=False)
    assert fake_completions.calls[1]["extra_body"] == {"reasoning": {"enabled": False}}


def test_budget_abort_mid_run(settings, pricing, fake_client):
    # cap เล็กมาก: call แรกผ่าน call ที่สองต้อง abort ก่อนสะสมความเสียหาย
    adapter = make_adapter(settings, pricing, fake_client, cap_usd=0.0003)
    adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "1"}])
    with pytest.raises(BudgetExceededError):
        adapter.chat(ModelTier.CROWD, [{"role": "user", "content": "2"}])


def test_missing_model_config_fails_at_construction(pricing, fake_client):
    incomplete = Settings(llm_model_crowd="", llm_model_analyst=ANALYST_MODEL, _env_file=None)
    with pytest.raises(AdapterConfigError, match="crowd"):
        LLMAdapter(incomplete, pricing, BudgetGuard(cap_usd=1.0), client=fake_client)
