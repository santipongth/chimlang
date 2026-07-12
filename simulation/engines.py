"""Engine registry (P6-M1) — จุดเดียวที่ประกาศ engine ที่มีให้เลือก

pattern จาก SwarmSight (registry + interface กลาง) แต่ engine ของเราต่างกันโดยเจตนา:
- fabric: กลไก diffusion deterministic ($0, reproduce 100%, scale 1,000) — ฐานของ what-if/fragility
- debate: agent LLM โพสต์โต้กันเป็นรอบ (เห็นบทสนทนา, cap 40, มีค่าใช้จ่ายผ่าน BudgetGuard)

MiroFish external adapter อยู่ในแผนระยะยาว (PHASE6-BRIEF) — เพิ่ม key ใหม่ที่นี่เมื่อถึงเวลา
โดยไม่แตะโค้ดผู้เรียก
"""

from dataclasses import dataclass

from core.config import get_settings


@dataclass(frozen=True)
class EngineInfo:
    key: str
    label_th: str
    label_en: str
    desc_th: str
    desc_en: str
    uses_llm: bool

    @property
    def max_agents(self) -> int:
        s = get_settings()
        return s.max_agents_per_debate if self.key == "debate" else s.max_agents_per_run

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label_th": self.label_th,
            "label_en": self.label_en,
            "desc_th": self.desc_th,
            "desc_en": self.desc_en,
            "uses_llm": self.uses_llm,
            "max_agents": self.max_agents,
        }


ENGINES: dict[str, EngineInfo] = {
    "fabric": EngineInfo(
        key="fabric",
        label_th="Fabric (กลไก)",
        label_en="Fabric (mechanistic)",
        desc_th=(
            "จำลองการแพร่/ความเชื่อแบบ deterministic — $0, reproduce ได้ 100%, "
            "สูงสุด 1,000 agents, fragility 5 จักรวาลเสมอ"
        ),
        desc_en=(
            "Deterministic diffusion/belief simulation — $0, fully reproducible, "
            "up to 1,000 agents, always 5-universe fragility"
        ),
        uses_llm=False,
    ),
    "debate": EngineInfo(
        key="debate",
        label_th="Debate (agent LLM)",
        label_en="Debate (LLM agents)",
        desc_th=(
            "agent คุยโต้กันเป็นรอบ เห็นบทสนทนาจริง + replay ได้ — "
            "ใช้ LLM (ผ่าน BudgetGuard), สูงสุด 40 agents"
        ),
        desc_en=(
            "Agents debate in rounds — real conversation + replay. "
            "Uses LLM (BudgetGuard-metered), up to 40 agents"
        ),
        uses_llm=True,
    ),
}


def get_engine(key: str) -> EngineInfo:
    if key not in ENGINES:
        raise ValueError(f"ไม่รู้จัก engine '{key}' (มี: {', '.join(ENGINES)})")
    return ENGINES[key]
