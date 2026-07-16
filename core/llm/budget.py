"""งบรวมต่อเดือน (P6-M5) — ติดตาม LLM spend สะสมทั้งเดือน แล้ว block ก่อนรันถ้าจะเกิน

ต่างจาก BudgetGuard (per-run cap ใน core/llm/cost.py) — ตัวนี้คุมยอด "สะสมทั้งเดือน"
persist ลง DB ทุก run ที่จ่ายจริง แล้วเช็คก่อนเริ่ม run ถัดไป
"""

from datetime import UTC, datetime

from core.db import connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_spend (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT NOT NULL DEFAULT '',
    usd DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS llm_spend_ts ON llm_spend (ts);
CREATE TABLE IF NOT EXISTS monthly_budget_reservations (
    reservation_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '24 hours',
    usd_reserved DOUBLE PRECISION NOT NULL CHECK (usd_reserved >= 0),
    usd_remaining DOUBLE PRECISION NOT NULL CHECK (usd_remaining >= 0),
    context TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS monthly_budget_reservations_active
    ON monthly_budget_reservations (created_at, expires_at)
    WHERE usd_remaining > 0;
"""

_BUDGET_LOCK_ID = 784_620_260_716


class MonthlyBudgetExceededError(RuntimeError):
    def __init__(self, spent: float, cap: float):
        super().__init__(
            f"งบรวมเดือนนี้ใช้หรือจองไป ${spent:.2f} จากเพดาน ${cap:.2f} — "
            "รันใหม่ถูกระงับจนกว่าจะขึ้นเดือนใหม่ "
            "หรือปรับเพดานในหน้าตั้งค่า"
        )


def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_this_month(dsn: str) -> float:
    with connection(dsn) as conn:
        row = conn.execute(
            "SELECT coalesce(sum(usd), 0) FROM llm_spend WHERE ts >= %s", (_month_start(),)
        ).fetchone()
    return float(row[0])


def reserved_this_month(dsn: str) -> float:
    """Return active reservations in this UTC budget month."""

    with connection(dsn) as conn:
        row = conn.execute(
            "SELECT coalesce(sum(usd_remaining), 0) FROM monthly_budget_reservations "
            "WHERE created_at >= %s AND expires_at > now() AND usd_remaining > 0",
            (_month_start(),),
        ).fetchone()
    return float(row[0])


def reserve_monthly_budget(
    dsn: str,
    reservations: dict[str, float],
    cap: float,
    *,
    context: str = "",
) -> float:
    """Atomically reserve a batch before any job is enqueued.

    A transaction-scoped advisory lock serializes all reservation decisions so two
    concurrent sweeps cannot both pass against the same remaining monthly budget.
    """

    cleaned = {str(key)[:160]: max(0.0, float(usd)) for key, usd in reservations.items()}
    cleaned = {key: usd for key, usd in cleaned.items() if key and usd > 0}
    if not cleaned:
        return 0.0
    requested = sum(cleaned.values())
    with connection(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_BUDGET_LOCK_ID,))
        spent = float(
            conn.execute(
                "SELECT coalesce(sum(usd), 0) FROM llm_spend WHERE ts >= %s",
                (_month_start(),),
            ).fetchone()[0]
        )
        reserved = float(
            conn.execute(
                "SELECT coalesce(sum(usd_remaining), 0) FROM monthly_budget_reservations "
                "WHERE created_at >= %s AND expires_at > now() AND usd_remaining > 0",
                (_month_start(),),
            ).fetchone()[0]
        )
        if cap > 0 and spent + reserved + requested > cap:
            raise MonthlyBudgetExceededError(spent + reserved, cap)
        for reservation_id, usd in cleaned.items():
            conn.execute(
                "INSERT INTO monthly_budget_reservations "
                "(reservation_id, usd_reserved, usd_remaining, context) VALUES (%s, %s, %s, %s)",
                (reservation_id, usd, usd, context[:160]),
            )
    return requested


def release_budget_reservation(dsn: str, reservation_id: str) -> float:
    """Release unused capacity and return the amount released."""

    if not reservation_id:
        return 0.0
    with connection(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_BUDGET_LOCK_ID,))
        row = conn.execute(
            "SELECT usd_remaining FROM monthly_budget_reservations "
            "WHERE reservation_id = %s FOR UPDATE",
            (reservation_id[:160],),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE monthly_budget_reservations SET usd_remaining = 0 "
                "WHERE reservation_id = %s",
                (reservation_id[:160],),
            )
    if row is None:
        return 0.0
    return max(0.0, float(row[0]))


def record_spend(
    dsn: str,
    usd: float,
    *,
    run_id: str = "",
    reservation_id: str = "",
) -> None:
    if usd <= 0:
        return
    with connection(dsn) as conn:
        if reservation_id:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (_BUDGET_LOCK_ID,))
        conn.execute("INSERT INTO llm_spend (run_id, usd) VALUES (%s, %s)", (run_id, usd))
        if reservation_id:
            conn.execute(
                "UPDATE monthly_budget_reservations "
                "SET usd_remaining = greatest(0, usd_remaining - %s) "
                "WHERE reservation_id = %s AND expires_at > now()",
                (usd, reservation_id[:160]),
            )


def check_monthly_budget(
    dsn: str,
    estimate_usd: float,
    cap: float,
    *,
    reservation_id: str = "",
) -> None:
    """เรียกก่อนเริ่ม run ที่ใช้ LLM — ยอดสะสม + estimate เกิน cap = ไม่เริ่ม"""
    if cap <= 0:
        return
    estimate = max(0.0, estimate_usd)
    with connection(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_BUDGET_LOCK_ID,))
        spent = float(
            conn.execute(
                "SELECT coalesce(sum(usd), 0) FROM llm_spend WHERE ts >= %s",
                (_month_start(),),
            ).fetchone()[0]
        )
        reserved = float(
            conn.execute(
                "SELECT coalesce(sum(usd_remaining), 0) FROM monthly_budget_reservations "
                "WHERE created_at >= %s AND expires_at > now() AND usd_remaining > 0",
                (_month_start(),),
            ).fetchone()[0]
        )
        own = 0.0
        if reservation_id:
            row = conn.execute(
                "SELECT usd_remaining FROM monthly_budget_reservations "
                "WHERE reservation_id = %s AND created_at >= %s AND expires_at > now()",
                (reservation_id[:160], _month_start()),
            ).fetchone()
            own = float(row[0]) if row else 0.0
        extra = max(0.0, estimate - own)
        if spent + reserved + extra > cap:
            raise MonthlyBudgetExceededError(spent + reserved, cap)
        if extra > 0 and reservation_id:
            if own > 0:
                conn.execute(
                    "UPDATE monthly_budget_reservations "
                    "SET usd_reserved = usd_reserved + %s, usd_remaining = usd_remaining + %s "
                    "WHERE reservation_id = %s",
                    (extra, extra, reservation_id[:160]),
                )
            else:
                conn.execute(
                    "INSERT INTO monthly_budget_reservations "
                    "(reservation_id, usd_reserved, usd_remaining, context) "
                    "VALUES (%s, %s, %s, 'runtime_extension') "
                    "ON CONFLICT (reservation_id) DO UPDATE SET "
                    "created_at = now(), expires_at = now() + interval '24 hours', "
                    "usd_reserved = excluded.usd_reserved, "
                    "usd_remaining = excluded.usd_remaining, context = excluded.context "
                    "WHERE monthly_budget_reservations.usd_remaining = 0 "
                    "OR monthly_budget_reservations.expires_at <= now() "
                    "OR monthly_budget_reservations.created_at < %s",
                    (reservation_id[:160], extra, extra, _month_start()),
                )
