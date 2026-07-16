"""Bounded, run-local reflection summaries for debate rounds.

Reflection is opt-in and ephemeral.  It has no autonomous long-term memory and
the policy hard-limits calls, input characters, and output tokens so its marginal
cost can be benchmarked honestly.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.llm.adapter import LLMAdapter, ModelTier
from core.text import sanitize_llm_text

REFLECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "agreements": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "disagreements": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "open_questions": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["agreements", "disagreements", "open_questions"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ReflectionPolicy:
    max_calls: int = 2
    max_input_chars: int = 2400
    max_output_tokens: int = 220

    def __post_init__(self) -> None:
        if not 0 <= self.max_calls <= 3:
            raise ValueError("reflection max_calls ต้องอยู่ใน 0..3")
        if not 400 <= self.max_input_chars <= 4000:
            raise ValueError("reflection max_input_chars ต้องอยู่ใน 400..4000")
        if not 80 <= self.max_output_tokens <= 320:
            raise ValueError("reflection max_output_tokens ต้องอยู่ใน 80..320")


class RunLocalReflector:
    def __init__(self, adapter: LLMAdapter, policy: ReflectionPolicy | None = None):
        self.adapter = adapter
        self.policy = policy or ReflectionPolicy()
        self.calls = 0
        self.summaries: list[dict] = []

    def reflect(self, *, subject: str, round_no: int, posts: list, seed: int) -> dict | None:
        if self.calls >= self.policy.max_calls:
            return None
        lines = [
            f"- [{p.segment}] ({p.move_type}) {p.content}"
            for p in posts
            if not p.failed and p.content
        ]
        digest = "\n".join(lines)[: self.policy.max_input_chars]
        if not digest:
            return None
        kwargs = (
            {"response_schema": REFLECTION_SCHEMA, "schema_name": "debate_reflection"}
            if self.adapter.supports_structured_outputs()
            else {}
        )
        result = self.adapter.chat(
            ModelTier.ANALYST,
            [
                {
                    "role": "system",
                    "content": (
                        "คุณสรุปการไตร่ตรองเฉพาะ run นี้ ตอบภาษาไทยเท่านั้น "
                        "ห้ามสร้างความจำระยะยาว ห้ามเพิ่มข้อเท็จจริงที่ไม่มีในโพสต์ และตอบ JSON ล้วน"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"หัวข้อ: {subject}\nรอบที่เพิ่งจบ: {round_no + 1}\n{digest}\n\n"
                        "สรุป agreements, disagreements, open_questions อย่างละไม่เกิน 3 ข้อ"
                    ),
                },
            ],
            max_tokens=self.policy.max_output_tokens,
            temperature=0,
            seed=seed + round_no,
            **kwargs,
        )
        import json

        parsed = json.loads(sanitize_llm_text(result.text))
        summary = {
            "round": round_no,
            "agreements": [str(x)[:240] for x in parsed.get("agreements", [])[:3]],
            "disagreements": [str(x)[:240] for x in parsed.get("disagreements", [])[:3]],
            "open_questions": [str(x)[:240] for x in parsed.get("open_questions", [])[:3]],
            "model_version": result.model,
            "parser_mode": result.structured_mode,
        }
        self.calls += 1
        self.summaries.append(summary)
        return summary

    def prompt_context(self) -> str:
        if not self.summaries:
            return ""
        latest = self.summaries[-1]
        parts = [
            "ข้อตกลงร่วม: " + "; ".join(latest["agreements"]),
            "ข้อขัดแย้ง: " + "; ".join(latest["disagreements"]),
            "คำถามค้าง: " + "; ".join(latest["open_questions"]),
        ]
        return "\n".join(part for part in parts if not part.endswith(": "))[:1200]


def reflection_benchmark(
    before: dict, after: dict, *, calls: int, policy: ReflectionPolicy
) -> dict:
    """Compare verifier output without hiding raw regressions behind one score."""

    before_errors = int(before.get("severity", {}).get("error", 0))
    after_errors = int(after.get("severity", {}).get("error", 0))
    before_warnings = int(before.get("severity", {}).get("warning", 0))
    after_warnings = int(after.get("severity", {}).get("warning", 0))
    return {
        "before": {"errors": before_errors, "warnings": before_warnings},
        "after": {"errors": after_errors, "warnings": after_warnings},
        "error_delta": after_errors - before_errors,
        "warning_delta": after_warnings - before_warnings,
        "calls": calls,
        "within_call_bound": calls <= policy.max_calls,
        "policy": {
            "max_calls": policy.max_calls,
            "max_input_chars": policy.max_input_chars,
            "max_output_tokens": policy.max_output_tokens,
        },
    }
