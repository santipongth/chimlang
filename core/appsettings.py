"""App settings (P6-M4) — ค่า default ของ UI (single-tenant ตามมติ D9)

เก็บเฉพาะ preference ที่ไม่ใช่ secret — webhook URL/API keys อยู่ .env เท่านั้น (กติกาเดิม)
"""

import json

import psycopg

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
}
_ALLOWED_KEYS = set(DEFAULTS)


def get_app_settings(dsn: str) -> dict:
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)
        row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    return {**DEFAULTS, **(row[0] if row else {})}


def put_app_settings(dsn: str, patch: dict) -> dict:
    unknown = set(patch) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(f"key ที่ไม่รู้จัก: {', '.join(sorted(unknown))}")
    if "default_engine" in patch and patch["default_engine"] not in ("fabric", "debate"):
        raise ValueError("default_engine ต้องเป็น fabric หรือ debate")
    if "default_agents" in patch and not (10 <= int(patch["default_agents"]) <= 1000):
        raise ValueError("default_agents ต้องอยู่ใน 10-1000")
    if "default_rounds" in patch and not (1 <= int(patch["default_rounds"]) <= 10):
        raise ValueError("default_rounds ต้องอยู่ใน 1-10")
    current = get_app_settings(dsn)
    merged = {**{k: v for k, v in current.items() if k in _ALLOWED_KEYS}, **patch}
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE app_settings SET data = %s WHERE id = 1",
            (json.dumps(merged, ensure_ascii=False),),
        )
    return merged
