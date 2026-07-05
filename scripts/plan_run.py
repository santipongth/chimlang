"""SIM-06 Fidelity Dial — แสดงแผน/ต้นทุนทุก preset ก่อนตัดสินใจรัน

uv run python scripts/plan_run.py
"""

from core.config import get_settings
from core.llm import PricingRegistry
from simulation.fidelity import PRESETS, plan_run


def main() -> None:
    settings = get_settings()
    pricing = PricingRegistry.from_yaml()
    print(f"Fidelity Dial (cap ช่วงพัฒนา: ≤ {settings.max_agents_per_run} agents)\n")
    print(f"{'preset':<10} {'agents':>6} {'rounds':>6} {'universes':>9} {'est cost':>10}  สถานะ")
    for name in PRESETS:
        plan = plan_run(name, settings, pricing)
        status = "รันได้" if plan.allowed_under_cap else f"ถูก block: {plan.blocked_reason}"
        print(
            f"{name:<10} {plan.preset.agents:>6} {plan.preset.rounds:>6} "
            f"{plan.preset.universes:>9} ${plan.est_cost_usd:>8.2f}  {status}"
        )
        print(f"{'':<10} → {plan.preset.marginal_accuracy_note}")


if __name__ == "__main__":
    main()
