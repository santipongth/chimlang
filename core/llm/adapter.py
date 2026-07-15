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
    structured_mode: str = "none"


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
        self._base_url = settings.llm_base_url or ""
        self._client = client or OpenAI(
            base_url=settings.llm_base_url or None,
            api_key=settings.llm_api_key,
            max_retries=3,
        )

    def model_for(self, tier: ModelTier) -> str:
        return self._models[tier]

    def supports_structured_outputs(self) -> bool:
        """Capability gate before adding JSON Schema parameters to a provider request."""
        base = self._base_url.lower()
        return "openrouter" in base or "api.openai.com" in base

    def chat(
        self,
        tier: ModelTier,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        seed: int | None = None,
        reasoning: bool | None = None,
        response_schema: dict | None = None,
        schema_name: str = "chimlang_response",
        allow_parser_fallback: bool = True,
    ) -> LLMResult:
        """reasoning=False ปิด hidden thinking ของ model (ผ่าน unified param ของ OpenRouter)

        วัดจริง 6 ก.ค. 2026: crowd model เผา ~1,200 thinking tokens/call (14.5s) ทั้งที่
        คำตอบมองเห็นแค่ ~50 ตัวอักษร — ปิดแล้วเหลือ 0.5s. ใช้กับ path ที่ interactive/สั้น
        (rehearsal, voice) เท่านั้น; งานคิดลึก (judge, hindcast, benchmark) ปล่อย default
        เพื่อไม่กระทบคุณภาพที่ benchmark ไว้ (ADR-0001)
        """
        model = self._models[tier]
        kwargs: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if seed is not None:
            kwargs["seed"] = seed  # reproducibility (NFR-07) — provider ที่รองรับจะ pin ได้
        extra_body: dict = {}
        if reasoning is not None:
            extra_body["reasoning"] = {"enabled": reasoning}
        structured_mode = "none"
        if response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name[:64],
                    "strict": True,
                    "schema": response_schema,
                },
            }
            structured_mode = "json_schema"
            # OpenRouter routes only to providers that support the requested parameter.
            if "openrouter" in self._base_url.lower():
                extra_body["provider"] = {"require_parameters": True}
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if not (
                response_schema is not None
                and allow_parser_fallback
                and self._structured_output_unsupported(exc)
            ):
                raise
            kwargs.pop("response_format", None)
            if extra_body.get("provider"):
                extra_body.pop("provider")
            if extra_body:
                kwargs["extra_body"] = extra_body
            else:
                kwargs.pop("extra_body", None)
            response = self._client.chat.completions.create(**kwargs)
            structured_mode = "parser_fallback_unsupported"

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
            structured_mode=structured_mode,
        )

    @staticmethod
    def _structured_output_unsupported(exc: Exception) -> bool:
        """Fallback only for an unsupported capability, never for an invalid schema."""
        text = str(exc).lower()
        if "schema" in text and "invalid" in text:
            return False
        return any(
            marker in text
            for marker in (
                "response_format",
                "structured output",
                "unsupported parameter",
                "does not support",
                "no endpoints found that support",
            )
        )
