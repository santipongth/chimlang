"""LLM adapter — ทางผ่านเดียวของทุก LLM call ในระบบ (SIM-07)

- OpenAI-compatible เท่านั้น: endpoint/key/model มาจาก env — ห้าม hardcode provider
- tiered routing: business logic ระบุแค่ tier (crowd/analyst) ไม่รู้จักชื่อ model
- ทุก call ถูกคิดเงินผ่าน BudgetGuard — แตะ cap แล้ว abort ทันที (กฎ Cost guard)
"""

import time
from dataclasses import dataclass
from enum import StrEnum

from openai import OpenAI

from core.config import Settings
from core.llm.budget import check_monthly_budget, record_spend
from core.llm.cost import BudgetGuard
from core.llm.pricing import PricingRegistry
from core.observability import provider_name, record_provider_call, traced


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
    finish_reason: str = ""  # "length" = โดนตัดที่ max_tokens — caller ใช้แยก truncation จาก schema พัง


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    dimension: int
    input_tokens: int
    cost_usd: float


class LLMAdapter:
    def __init__(
        self,
        settings: Settings,
        pricing: PricingRegistry,
        guard: BudgetGuard,
        client: OpenAI | None = None,
        run_id: str = "",
        monthly_cap_usd: float = 0.0,
        monthly_reservation_id: str = "",
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
        self._embedding_model = settings.llm_model_embedding.strip()
        self._embedding_dimension = int(settings.llm_embedding_dimension)
        self._dsn = settings.postgres_url
        self._run_id = run_id
        self._monthly_cap_usd = max(0.0, monthly_cap_usd)
        self._monthly_reservation_id = monthly_reservation_id[:160]
        self._provider = provider_name(self._base_url)
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

    def supports_embeddings(self) -> bool:
        return bool(self._embedding_model)

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    @property
    def embedding_dimension(self) -> int:
        return self._embedding_dimension

    def bind_run(self, run_id: str) -> None:
        """Attach safe operational lineage before calls; no prompt/content is recorded."""
        self._run_id = run_id[:160]

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
        self._guard.ensure_open()
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

        started = time.monotonic()
        try:
            with traced("llm.chat", provider=self._provider, tier=tier.value):
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
        except Exception as exc:
            record_provider_call(
                self._dsn,
                run_id=self._run_id,
                provider=self._provider,
                operation="chat",
                tier=tier.value,
                status="error",
                latency_s=time.monotonic() - started,
                error_kind=type(exc).__name__,
                model_version=model,
            )
            raise

        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost_usd = self._pricing.cost_usd(model, input_tokens, output_tokens)
        record_provider_call(
            self._dsn,
            run_id=self._run_id,
            provider=self._provider,
            operation="chat",
            tier=tier.value,
            status="success",
            latency_s=time.monotonic() - started,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            model_version=response.model or model,
        )
        if self._run_id:
            # Per-call ledger includes failed runs and calls that exhaust the runtime cap.
            record_spend(
                self._dsn,
                cost_usd,
                run_id=self._run_id,
                reservation_id=self._monthly_reservation_id,
            )
        # คิดเงินก่อน return — ถ้าแตะ cap จะ raise BudgetExceededError = abort run
        self._guard.add_actual(cost_usd)

        return LLMResult(
            text=response.choices[0].message.content or "",
            model=response.model or model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            structured_mode=structured_mode,
            finish_reason=str(getattr(response.choices[0], "finish_reason", "") or ""),
        )

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Create evidence embeddings through the same priced, guarded provider path."""

        if not texts:
            return EmbeddingResult((), self._embedding_model, self._embedding_dimension, 0, 0.0)
        if not self._embedding_model:
            raise AdapterConfigError("ยังไม่ได้ตั้งค่า embedding model")
        clean = [str(text)[:12000] for text in texts]
        # Thai can tokenize close to one code point/token, so use chars as a conservative bound.
        estimated_tokens = sum(max(1, len(text)) for text in clean)
        estimated_cost = self._pricing.cost_usd(self._embedding_model, estimated_tokens, 0)
        self._guard.check_additional(estimated_cost)
        if self._run_id and self._monthly_cap_usd > 0:
            check_monthly_budget(
                self._dsn,
                estimated_cost,
                self._monthly_cap_usd,
                reservation_id=self._monthly_reservation_id,
            )
        started = time.monotonic()
        try:
            with traced(
                "llm.embedding",
                provider=self._provider,
                tier="embedding",
                input_count=len(clean),
            ):
                response = self._client.embeddings.create(
                    model=self._embedding_model,
                    input=clean,
                    dimensions=self._embedding_dimension,
                )
        except Exception as exc:
            record_provider_call(
                self._dsn,
                run_id=self._run_id,
                provider=self._provider,
                operation="embedding",
                tier="embedding",
                status="error",
                latency_s=time.monotonic() - started,
                error_kind=type(exc).__name__,
                model_version=self._embedding_model,
            )
            raise
        vectors = tuple(tuple(float(value) for value in item.embedding) for item in response.data)
        dimension = len(vectors[0]) if vectors else 0
        if len(vectors) != len(clean) or not dimension or any(len(v) != dimension for v in vectors):
            raise AdapterConfigError("embedding provider คืน vector shape ไม่ครบ")
        if dimension != self._embedding_dimension:
            raise AdapterConfigError(
                f"embedding dimension ไม่ตรง: ได้ {dimension}, ตั้งไว้ {self._embedding_dimension}"
            )
        usage = getattr(response, "usage", None)
        input_tokens = int(
            getattr(usage, "prompt_tokens", 0) or getattr(usage, "total_tokens", 0) or 0
        )
        cost_usd = self._pricing.cost_usd(self._embedding_model, input_tokens, 0)
        model_version = getattr(response, "model", "") or self._embedding_model
        record_provider_call(
            self._dsn,
            run_id=self._run_id,
            provider=self._provider,
            operation="embedding",
            tier="embedding",
            status="success",
            latency_s=time.monotonic() - started,
            input_tokens=input_tokens,
            cost_usd=cost_usd,
            model_version=model_version,
        )
        if self._run_id:
            record_spend(
                self._dsn,
                cost_usd,
                run_id=self._run_id,
                reservation_id=self._monthly_reservation_id,
            )
        self._guard.add_actual(cost_usd)
        return EmbeddingResult(vectors, model_version, dimension, input_tokens, cost_usd)

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
