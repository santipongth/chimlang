"""fixtures ร่วม: fake OpenAI-compatible client + pricing/settings มาตรฐานสำหรับ test"""

from types import SimpleNamespace

import pytest

from core.config import Settings
from core.llm import ModelPricing, PricingRegistry

CROWD_MODEL = "test/crowd-flash"
ANALYST_MODEL = "test/analyst-max"


class FakeCompletions:
    """จำลอง client.chat.completions ของ OpenAI SDK — บันทึกทุก call ที่รับเข้ามา"""

    def __init__(self, *, prompt_tokens=100, completion_tokens=20, content="สวัสดีครับ"):
        self.calls: list[dict] = []
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._content = content

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
            ),
            model=kwargs["model"],
        )


class FakeClient:
    def __init__(self, completions: FakeCompletions):
        self.chat = SimpleNamespace(completions=completions)


@pytest.fixture
def fake_completions() -> FakeCompletions:
    return FakeCompletions()


@pytest.fixture
def fake_client(fake_completions) -> FakeClient:
    return FakeClient(fake_completions)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        llm_base_url="https://example.invalid/v1",
        llm_api_key="test-key",
        llm_model_crowd=CROWD_MODEL,
        llm_model_analyst=ANALYST_MODEL,
        run_budget_usd_cap=5.0,
        _env_file=None,  # กัน .env จริงรั่วเข้า test
    )


@pytest.fixture
def pricing() -> PricingRegistry:
    return PricingRegistry(
        {
            # เลขกลมๆ ให้คำนวณมือได้: crowd 1/4, analyst 10/40 USD ต่อ 1M token
            CROWD_MODEL: ModelPricing(input_usd_per_m=1.0, output_usd_per_m=4.0),
            ANALYST_MODEL: ModelPricing(input_usd_per_m=10.0, output_usd_per_m=40.0),
        }
    )
