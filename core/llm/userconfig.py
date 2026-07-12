"""LLM ปรับเองได้จากหน้าตั้งค่า (มติผู้ใช้ 12 ก.ค. 2569 — ดู ADR-0006)

ขอบเขตที่ตั้งจาก UI ได้: provider preset, base URL, ชื่อ model (crowd/analyst),
ราคา token ของ model ที่ผู้ใช้เพิ่มเอง — เก็บใน app_settings (ไม่ใช่ secret)

**API key ยังอยู่ .env เท่านั้น** (LLM_API_KEY — กติกา secrets ของ repo ไม่เปลี่ยน)
และ fail-closed เดิมคงอยู่: model ที่ไม่มีราคา (ทั้งใน pricing.yaml และที่ผู้ใช้กรอก)
= รันไม่ได้ เพื่อไม่ให้ BudgetGuard ตาบอด
"""

from core.config import Settings, get_settings
from core.llm.pricing import PricingRegistry

# provider ยอดนิยมที่เข้ากับ OpenAI-compatible API (SIM-07) — base_url เติมให้อัตโนมัติ
LLM_PROVIDERS: dict[str, dict] = {
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
        "hint_th": "รวมหลายค่ายในคีย์เดียว (ค่าเริ่มต้นของโครงการ)",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
        "hint_th": "GPT ทุกรุ่นจาก OpenAI โดยตรง",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "needs_key": True,
        "hint_th": "โมเดลโอเพนซอร์สความเร็วสูง",
    },
    "together": {
        "label": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "needs_key": True,
        "hint_th": "โมเดลโอเพนซอร์สหลากหลาย",
    },
    "ollama": {
        "label": "Ollama",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
        "hint_th": "รันโมเดลบนเครื่องตัวเอง — ข้อมูลไม่ออกนอกเครื่อง (ราคา token = 0)",
    },
    "custom": {
        "label": "กำหนดเอง",
        "base_url": "",
        "needs_key": True,
        "hint_th": "บริการอื่นที่เข้ากับ OpenAI API",
    },
}

_LLM_SETTINGS_KEYS = ("llm_base_url", "llm_model_crowd", "llm_model_analyst")


def _load_app_llm(dsn: str) -> dict:
    from core.appsettings import get_app_settings

    try:
        return get_app_settings(dsn)
    except Exception:
        return {}


def effective_llm_settings() -> Settings:
    """Settings ที่ overlay ค่าจากหน้าตั้งค่าทับ .env — ค่าว่างใน UI = ใช้ .env ตามเดิม"""
    base = get_settings()
    app = _load_app_llm(base.postgres_url)
    overrides = {k: app[k] for k in _LLM_SETTINGS_KEYS if str(app.get(k, "")).strip()}
    return get_settings(**overrides) if overrides else base


def effective_pricing() -> PricingRegistry:
    """ตารางราคาจาก yaml + ราคาที่ผู้ใช้กรอกเพิ่ม (fail-closed: ไม่มีราคา = รันไม่ได้)"""
    base = get_settings()
    app = _load_app_llm(base.postgres_url)
    return PricingRegistry.from_yaml().merged(app.get("llm_prices") or {})
