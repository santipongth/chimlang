"""LLM adapter — ทางผ่านเดียวของทุก LLM call ในระบบ (SIM-07)

- OpenAI-compatible เท่านั้น: endpoint/key/model มาจาก env — ห้าม hardcode provider
- tiered routing: business logic ระบุแค่ tier (crowd/analyst) ไม่รู้จักชื่อ model
- ทุก call ถูกคิดเงินผ่าน BudgetGuard — แตะ cap แล้ว abort ทันที (กฎ Cost guard)
"""

from dataclasses import dataclass
from enum import StrEnum

from openai import OpenAI

from core.config import Settings
from core.llm.cost import BudgetGuard
from core.llm.pricing import PricingRegistry


class ModelTier(StrEnum):
    CROWD = "crowd"
    ANALYST = "analyst"


class AdapterConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMAdapter:
    def __init__(
        self,
        settings: Settings,
        pricing: PricingRegistry,
        guard: BudgetGuard,
        client: OpenAI | None = None,
    ):
        self._models = {
            ModelTier.CROWD: settings.llm_model_crowd,
            ModelTier.ANALYST: settings.llm_model_analyst,
        }
        missing = [tier.value for tier, model in self._models.items() if not model]
        if missing:
            raise AdapterConfigError(
                f"ยังไม่ได้ตั้งค่า model สำหรับ tier: {', '.join(missing)} "
                "(ดู LLM_MODEL_CROWD / LLM_MODEL_ANALYST ใน .env)"
            )
        self._pricing = pricing
        self._guard = guard
        self._client = client or OpenAI(
            base_url=settings.llm_base_url or None,
            api_key=settings.llm_api_key,
            max_retries=3,
        )

    def model_for(self, tier: ModelTier) -> str:
        return self._models[tier]

    def chat(
        self,
        tier: ModelTier,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> LLMResult:
        model = self._models[tier]
        kwargs: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if seed is not None:
            kwargs["seed"] = seed  # reproducibility (NFR-07) — provider ที่รองรับจะ pin ได้

        response = self._client.chat.completions.create(**kwargs)

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost_usd = self._pricing.cost_usd(model, input_tokens, output_tokens)
        # คิดเงินก่อน return — ถ้าแตะ cap จะ raise BudgetExceededError = abort run
        self._guard.add_actual(cost_usd)

        return LLMResult(
            text=response.choices[0].message.content or "",
            model=response.model or model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
