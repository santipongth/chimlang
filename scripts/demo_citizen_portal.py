"""Explicit offline demo for the legacy Citizen portal; never mounted by the API."""

from core.config import get_settings
from simulation.citizen import CitizenInputs, build_impact_twin, render_citizen_portal
from simulation.persona import PersonaFactory


def main() -> None:
    settings = get_settings()
    sample = CitizenInputs(
        income_band="15k-30k",
        region="ชานเมือง",
        commute="รถยนต์ส่วนตัว",
        occupation="พนักงานออฟฟิศ",
        age_band="31-45",
        household_size=3,
    )
    twin = build_impact_twin(
        sample,
        PersonaFactory(),
        max_agents=settings.max_agents_per_run,
        seed=settings.default_seed,
    )
    print(render_citizen_portal("DEMO: มาตรการค่าธรรมเนียมรถติด กทม.", twin, []))


if __name__ == "__main__":
    main()
