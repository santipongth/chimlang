"""App settings (P6-M4) — ค่า default ของ UI (single-tenant ตามมติ D9)

เก็บเฉพาะ preference ที่ไม่ใช่ secret — webhook URL/API keys อยู่ .env เท่านั้น (กติกาเดิม)
"""

import json

from core.db import connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    id INT PRIMARY KEY CHECK (id = 1),
    data JSONB NOT NULL DEFAULT '{}'
);
INSERT INTO app_settings (id, data) VALUES (1, '{}') ON CONFLICT (id) DO NOTHING;
"""

DEFAULTS: dict = {
    "default_engine": "fabric",
    "default_agents": 100,
    "default_rounds": 3,
    "default_domain": "นโยบายสาธารณะ",
    "default_tab": "overview",
    # LLM ปรับเองได้ (ADR-0006/0007) — ค่าว่าง = ใช้ .env
    "llm_provider": "",
    "llm_base_url": "",
    "llm_model_crowd": "",
    "llm_model_analyst": "",
    "llm_prices": {},  # model -> {input_usd_per_m, output_usd_per_m} (แก้ราคามาตรฐาน/เพิ่มใหม่ได้)
    # API key เก็บ **ciphertext** (ADR-0007) — เขียนผ่าน set_llm_api_key() เท่านั้น ห้าม PUT ตรง
    "llm_api_key_enc": "",
    # งบ (P6-M5) — 0 = ใช้ค่า .env; > 0 = ทับ
    "run_budget_usd_cap": 0.0,
    "monthly_budget_usd_cap": 0.0,
    # News Desk (P7) — ค่าว่าง = ใช้ .env; feeds คั่นด้วย , | Tavily key เก็บ ciphertext (ADR-0007)
    "news_rss_feeds": "",
    "tavily_api_key_enc": "",
}
_ALLOWED_KEYS = set(DEFAULTS)
# key ที่ห้ามแก้ผ่าน PUT /settings.json ปกติ (มี endpoint แยกที่จัดการเข้ารหัส/มาสก์)
_PROTECTED_KEYS = {"llm_api_key_enc", "tavily_api_key_enc"}


def get_app_settings(dsn: str) -> dict:
    with connection(dsn) as conn:
        row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    return {**DEFAULTS, **(row[0] if row else {})}


def put_app_settings(dsn: str, patch: dict) -> dict:
    unknown = set(patch) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(f"key ที่ไม่รู้จัก: {', '.join(sorted(unknown))}")
    protected = set(patch) & _PROTECTED_KEYS
    if protected:
        raise ValueError(f"ต้องตั้งผ่าน endpoint เฉพาะ: {', '.join(sorted(protected))}")
    for k in ("run_budget_usd_cap", "monthly_budget_usd_cap"):
        if k in patch and not (0 <= float(patch[k]) <= 100000):
            raise ValueError(f"{k} ต้องอยู่ใน 0-100000 (0 = ใช้ค่า .env)")
    if "default_engine" in patch and patch["default_engine"] not in ("fabric", "debate"):
        raise ValueError("default_engine ต้องเป็น fabric หรือ debate")
    if "default_agents" in patch and not (10 <= int(patch["default_agents"]) <= 1000):
        raise ValueError("default_agents ต้องอยู่ใน 10-1000")
    if "default_rounds" in patch and not (1 <= int(patch["default_rounds"]) <= 10):
        raise ValueError("default_rounds ต้องอยู่ใน 1-10")
    if "llm_provider" in patch and patch["llm_provider"]:
        from core.llm.userconfig import LLM_PROVIDERS

        if patch["llm_provider"] not in LLM_PROVIDERS:
            raise ValueError(f"ไม่รู้จัก provider: {patch['llm_provider']}")
    for k in ("llm_base_url", "llm_model_crowd", "llm_model_analyst"):
        if k in patch and not isinstance(patch[k], str):
            raise ValueError(f"{k} ต้องเป็นข้อความ")
    if "llm_base_url" in patch and patch["llm_base_url"]:
        if not str(patch["llm_base_url"]).startswith(("http://", "https://")):
            raise ValueError("base URL ต้องขึ้นต้นด้วย http(s)://")
    if "llm_prices" in patch:
        prices = patch["llm_prices"]
        if not isinstance(prices, dict):
            raise ValueError("llm_prices ต้องเป็น object")
        for model, e in prices.items():
            try:
                i, o = float(e["input_usd_per_m"]), float(e["output_usd_per_m"])
            except (KeyError, TypeError, ValueError) as err:
                raise ValueError(
                    f"ราคาของ {model} ต้องมี input_usd_per_m/output_usd_per_m เป็นตัวเลข"
                ) from err
            if i < 0 or o < 0 or i > 1000 or o > 1000:
                raise ValueError(f"ราคาของ {model} ต้องอยู่ใน 0-1000 USD ต่อ 1 ล้าน token")
    current = get_app_settings(dsn)
    merged = {**{k: v for k, v in current.items() if k in _ALLOWED_KEYS}, **patch}
    with connection(dsn) as conn:
        conn.execute(
            "UPDATE app_settings SET data = %s WHERE id = 1",
            (json.dumps(merged, ensure_ascii=False),),
        )
    return merged


def _set_encrypted(dsn: str, field: str, plaintext: str) -> None:
    """เก็บ secret แบบเข้ารหัสในช่อง protected (ADR-0007) — ว่าง = ลบ (กลับไปใช้ .env)"""
    from core.secretbox import encrypt

    enc = encrypt(plaintext) if plaintext.strip() else ""
    current = get_app_settings(dsn)
    current[field] = enc
    with connection(dsn) as conn:
        conn.execute(
            "UPDATE app_settings SET data = %s WHERE id = 1",
            (json.dumps(current, ensure_ascii=False),),
        )


def _get_encrypted(dsn: str, field: str) -> str:
    from core.secretbox import decrypt

    enc = get_app_settings(dsn).get(field, "")
    return decrypt(enc) if enc else ""


def set_llm_api_key(dsn: str, plaintext: str) -> None:
    _set_encrypted(dsn, "llm_api_key_enc", plaintext)


def get_llm_api_key(dsn: str) -> str:
    """ถอดรหัส key ที่เก็บไว้ — ไม่มี = '' (ผู้เรียก fallback .env เอง)"""
    return _get_encrypted(dsn, "llm_api_key_enc")


def set_tavily_api_key(dsn: str, plaintext: str) -> None:
    _set_encrypted(dsn, "tavily_api_key_enc", plaintext)


def get_tavily_api_key(dsn: str) -> str:
    return _get_encrypted(dsn, "tavily_api_key_enc")
