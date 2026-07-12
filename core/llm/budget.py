"""งบรวมต่อเดือน (P6-M5) — ติดตาม LLM spend สะสมทั้งเดือน แล้ว block ก่อนรันถ้าจะเกิน

ต่างจาก BudgetGuard (per-run cap ใน core/llm/cost.py) — ตัวนี้คุมยอด "สะสมทั้งเดือน"
persist ลง DB ทุก run ที่จ่ายจริง แล้วเช็คก่อนเริ่ม run ถัดไป
"""

from datetime import UTC, datetime

import psycopg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_spend (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT NOT NULL DEFAULT '',
    usd DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS llm_spend_ts ON llm_spend (ts);
"""


class MonthlyBudgetExceededError(RuntimeError):
    def __init__(self, spent: float, cap: float):
        super().__init__(
            f"งบรวมเดือนนี้ใช้ไป ${spent:.2f} จากเพดาน ${cap:.2f} — รันใหม่ถูกระงับจนกว่าจะขึ้นเดือนใหม่ "
            "หรือปรับเพดานในหน้าตั้งค่า"
        )


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_this_month(dsn: str) -> float:
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)
        row = conn.execute(
            "SELECT coalesce(sum(usd), 0) FROM llm_spend WHERE ts >= %s", (_month_start(),)
        ).fetchone()
    return float(row[0])


def record_spend(dsn: str, usd: float, *, run_id: str = "") -> None:
    if usd <= 0:
        return
    with psycopg.connect(dsn) as conn:
        conn.execute(_SCHEMA)
        conn.execute("INSERT INTO llm_spend (run_id, usd) VALUES (%s, %s)", (run_id, usd))


def check_monthly_budget(dsn: str, estimate_usd: float, cap: float) -> None:
    """เรียกก่อนเริ่ม run ที่ใช้ LLM — ยอดสะสม + estimate เกิน cap = ไม่เริ่ม"""
    if cap <= 0:
        return
    projected = spent_this_month(dsn) + max(0.0, estimate_usd)
    if projected > cap:
        raise MonthlyBudgetExceededError(spent_this_month(dsn), cap)
