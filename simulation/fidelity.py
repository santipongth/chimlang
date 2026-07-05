"""Fidelity Dial (SIM-06) — Quick / Standard / Deep พร้อม cost estimate ก่อนรัน

presets ตาม PRD; ทุกแผนต้องผ่าน cap ช่วงพัฒนา (≤ 10 agents) — dial มีไว้ครบโครงสร้าง
ตั้งแต่วันนี้ เพื่อให้วันที่ผู้ใช้สั่งขยาย scale แค่ยกเลิก cap แล้วใช้ได้ทันที
"""

from dataclasses import dataclass

from core.config import Settings
from core.llm import CostEstimator, PricingRegistry, TierLoad


class PlanBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class FidelityPreset:
    name: str
    agents: int
    rounds: int
    universes: int
    voice_ratio: float  # สัดส่วน agent-rounds ที่เรียก LLM voice (ประหยัด = เฉพาะเหตุการณ์สำคัญ)
    marginal_accuracy_note: str


PRESETS: dict[str, FidelityPreset] = {
    "dev": FidelityPreset(
        "dev", 10, 30, 5, 0.3, "สำหรับพัฒนา/ทดสอบ — สัญญาณเชิงทิศทางเท่านั้น (cap ปัจจุบัน)"
    ),
    "quick": FidelityPreset("quick", 100, 10, 5, 0.2, "ภาพรวมหยาบ เร็ว — เหมาะ scoping ก่อนรันจริง"),
    "standard": FidelityPreset(
        "standard", 1000, 30, 5, 0.15, "มาตรฐานรายงาน — สมดุลความละเอียด/ต้นทุน"
    ),
    "deep": FidelityPreset(
        "deep", 5000, 50, 5, 0.10, "ละเอียดสุด — marginal accuracy เพิ่มไม่มากแต่ต้นทุน ~10x standard"
    ),
}

# สมมติฐาน token ต่อ voice call (calibrate จาก demo จริง 5 ก.ค. 2026: ~700 in / 250 out)
VOICE_INPUT_TOKENS = 700
VOICE_OUTPUT_TOKENS = 250


@dataclass(frozen=True)
class RunPlan:
    preset: FidelityPreset
    est_cost_usd: float
    allowed_under_cap: bool
    blocked_reason: str | None


def plan_run(preset_name: str, settings: Settings, pricing: PricingRegistry) -> RunPlan:
    preset = PRESETS[preset_name]
    voice_calls = int(preset.agents * preset.rounds * preset.voice_ratio) * preset.universes
    estimate = CostEstimator(pricing).estimate(
        [
            TierLoad(
                settings.llm_model_crowd,
                calls=voice_calls,
                avg_input_tokens=VOICE_INPUT_TOKENS,
                avg_output_tokens=VOICE_OUTPUT_TOKENS,
            )
        ]
    )
    allowed = preset.agents <= settings.max_agents_per_run
    return RunPlan(
        preset=preset,
        est_cost_usd=estimate.total_usd,
        allowed_under_cap=allowed,
        blocked_reason=None
        if allowed
        else (
            f"agents {preset.agents} เกิน cap ต่อ run ({settings.max_agents_per_run}) — "
            "ระดับนี้ต้องขออนุมัติผู้ใช้ก่อน"
        ),
    )


def ensure_plan_allowed(plan: RunPlan) -> None:
    """gate ก่อนรันจริง — preset ที่เกิน cap ต้องหยุดตั้งแต่ขั้นวางแผน"""
    if not plan.allowed_under_cap:
        raise PlanBlockedError(plan.blocked_reason)
