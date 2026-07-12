"""การตั้งค่าจาก environment (.env) — secrets อยู่ใน env เท่านั้น ห้าม hardcode"""

import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

# Windows console default = cp1252 พิมพ์ไทยพัง — บังคับ UTF-8 ที่จุดเดียว
# (ทุก script import core.config อยู่แล้ว จึงไม่ต้องตั้ง PYTHONIOENCODING อีกต่อไป)
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass  # stream ถูก redirect/ปิด — ข้ามได้


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (tiered ตาม TECH-DECISIONS D5) ---
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_crowd: str = ""
    llm_model_analyst: str = ""

    # --- Cost guard / reproducibility ---
    run_budget_usd_cap: float = 5.0
    default_seed: int = 42
    # cap ต่อ run: ผู้ใช้สั่งขยาย scale 6 ก.ค. 2026 (เดิม 10 ช่วง Phase 0-2) → 1,000 (standard)
    # ระดับ deep (5,000) ยังต้องขออนุมัติผู้ใช้ก่อน — BudgetGuard เป็นด่านต้นทุนจริงเสมอ
    max_agents_per_run: int = 1000

    # --- Datastores ---
    postgres_url: str = "postgresql://chimlang:chimlang@localhost:5432/chimlang"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # --- Governance flags (default ปลอดภัย ห้ามปิดใน production) ---
    pii_detector_enabled: bool = True
    watermark_enabled: bool = True
    # --- Auth/RBAC ที่ API (GOV-06, P4-M4) ---
    # dev default = ปิด (ทุก request เป็น dev-admin) — production ต้องเปิด + ตั้ง API_KEYS
    auth_enabled: bool = False
    api_keys: str = ""  # "คีย์:ผู้ใช้:role[:verified],..." — role: viewer|analyst|operator|admin

    # --- Watchlist alerts (P5-M5) ---
    # webhook URL เป็น secret → อยู่ .env เท่านั้น ห้ามเก็บใน DB/ห้าม log (https เท่านั้น)
    alert_webhook_url: str = ""
    consensus_shift_threshold: float = 0.10  # |Δ mean_delta| ระหว่างรอบ ≥ ค่านี้ = consensus_shift


def get_settings(**overrides) -> Settings:
    return Settings(**overrides)
