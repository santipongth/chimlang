"""การตั้งค่าจาก environment (.env) — secrets อยู่ใน env เท่านั้น ห้าม hardcode"""

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- Datastores ---
    postgres_url: str = "postgresql://chimlang:chimlang@localhost:5432/chimlang"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # --- Governance flags (default ปลอดภัย ห้ามปิดใน production) ---
    pii_detector_enabled: bool = True
    watermark_enabled: bool = True


def get_settings(**overrides) -> Settings:
    return Settings(**overrides)
