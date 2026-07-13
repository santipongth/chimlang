"""Watchlist + Alerts (P5-M5) — retention loop: ติดตามคำถามเดิมซ้ำตาม cadence

ต่อยอด REH-05 (Divergence Alarm ใน war room ทำงานเฉพาะช่วง incident):
watchlist ทำงานถาวร — ผู้ใช้ subscribe หัวข้อ ระบบ re-run ตามรอบ (daily/weekly)
แล้วแจ้งเตือนเมื่อ (1) พบ tipping point (2) ข้อสรุปเปลี่ยนทิศจากรอบก่อน ≥ threshold

ต่างจาก audit/registry: watchlists/alerts เป็นตาราง operational แก้สถานะได้
(toggle active, mark read) — ไม่ใช่ governance record จึงไม่ติด append-only trigger
แต่ทุกการรันจาก watchlist ยัง append audit log ตามปกติ
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from core.config import get_settings
from governance.webhook import fire_webhook

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlists (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    label TEXT NOT NULL,
    subject TEXT NOT NULL,
    agents INT NOT NULL DEFAULT 100,
    cadence TEXT NOT NULL DEFAULT 'daily' CHECK (cadence IN ('daily', 'weekly')),
    active BOOLEAN NOT NULL DEFAULT true,
    last_run_at TIMESTAMPTZ,
    last_delta DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    watchlist_id BIGINT REFERENCES watchlists(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    read_at TIMESTAMPTZ
);
"""

CADENCE_HOURS = {"daily": 24, "weekly": 24 * 7}


@dataclass(frozen=True)
class Watchlist:
    id: int
    label: str
    subject: str
    agents: int
    cadence: str
    active: bool
    last_run_at: str | None
    last_delta: float | None


class WatchlistStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    # --- watchlists ---

    def create(self, *, label: str, subject: str, agents: int, cadence: str) -> int:
        if cadence not in CADENCE_HOURS:
            raise ValueError("cadence ต้องเป็น daily หรือ weekly")
        with self._conn() as conn:
            row = conn.execute(
                "INSERT INTO watchlists (label, subject, agents, cadence) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (label, subject, agents, cadence),
            ).fetchone()
            return int(row[0])

    def list_watchlists(self) -> list[Watchlist]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, label, subject, agents, cadence, active, last_run_at, last_delta "
                "FROM watchlists ORDER BY created_at DESC"
            ).fetchall()
        return [
            Watchlist(
                id=r[0],
                label=r[1],
                subject=r[2],
                agents=r[3],
                cadence=r[4],
                active=r[5],
                last_run_at=r[6].isoformat() if r[6] else None,
                last_delta=float(r[7]) if r[7] is not None else None,
            )
            for r in rows
        ]

    def get(self, watchlist_id: int) -> Watchlist:
        found = [w for w in self.list_watchlists() if w.id == watchlist_id]
        if not found:
            raise ValueError(f"ไม่พบ watchlist id {watchlist_id}")
        return found[0]

    def set_active(self, watchlist_id: int, active: bool) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE watchlists SET active = %s WHERE id = %s", (active, watchlist_id))

    def delete(self, watchlist_id: int) -> None:
        """ลบ watchlist (alerts ตามไปด้วยผ่าน ON DELETE CASCADE) — ตาราง operational
        ไม่ใช่ governance record (ดู docstring หัวไฟล์); run ที่เคยเกิดยังอยู่ใน audit ตามปกติ"""
        with self._conn() as conn:
            row = conn.execute(
                "DELETE FROM watchlists WHERE id = %s RETURNING id", (watchlist_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ watchlist id {watchlist_id}")

    def touch_run(self, watchlist_id: int, delta: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE watchlists SET last_run_at = now(), last_delta = %s WHERE id = %s",
                (delta, watchlist_id),
            )

    def due(self, now: datetime | None = None) -> list[Watchlist]:
        """watchlist ที่ active และถึงรอบตาม cadence (ยังไม่เคยรัน = ถึงรอบทันที)"""
        now = now or datetime.now(UTC)
        out = []
        for w in self.list_watchlists():
            if not w.active:
                continue
            if w.last_run_at is None:
                out.append(w)
                continue
            last = datetime.fromisoformat(w.last_run_at)
            if now - last >= timedelta(hours=CADENCE_HOURS[w.cadence]):
                out.append(w)
        return out

    # --- alerts ---

    def insert_alert(self, watchlist_id: int | None, kind: str, payload: dict) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "INSERT INTO alerts (watchlist_id, kind, payload) VALUES (%s, %s, %s) RETURNING id",
                (watchlist_id, kind, json.dumps(payload, ensure_ascii=False)),
            ).fetchone()
            return int(row[0])

    def list_alerts(self, *, unread_only: bool = False, limit: int = 50) -> list[dict]:
        q = "SELECT id, ts, watchlist_id, kind, payload, read_at FROM alerts"
        if unread_only:
            q += " WHERE read_at IS NULL"
        q += " ORDER BY ts DESC LIMIT %s"
        with self._conn() as conn:
            rows = conn.execute(q, (limit,)).fetchall()
        return [
            {
                "id": r[0],
                "ts": r[1].isoformat(),
                "watchlist_id": r[2],
                "kind": r[3],
                "payload": r[4],
                "read": r[5] is not None,
            }
            for r in rows
        ]

    def mark_read(self, alert_id: int | None = None, *, all_alerts: bool = False) -> None:
        with self._conn() as conn:
            if all_alerts:
                conn.execute("UPDATE alerts SET read_at = now() WHERE read_at IS NULL")
            elif alert_id is not None:
                conn.execute("UPDATE alerts SET read_at = now() WHERE id = %s", (alert_id,))


# --- ตรวจหนึ่ง watchlist: รัน → เทียบรอบก่อน → alert + webhook ---

# runner คืน {"mean_delta": float, "tipping": [dict, ...]} — แยกเป็น callable เพื่อ test ได้
Runner = Callable[[str, int], dict]


def check_watchlist(store: WatchlistStore, w: Watchlist, *, runner: Runner) -> list[dict]:
    """รันหนึ่งรอบ + สร้าง alert ตามเงื่อนไข — webhook เป็น best-effort เสมอ"""
    threshold = get_settings().consensus_shift_threshold
    result = runner(w.subject, w.agents)
    created: list[dict] = []

    if result.get("tipping"):
        biggest = max(result["tipping"], key=lambda t: abs(t.get("delta", 0)))
        payload = {
            "subject": w.subject,
            "watchlist_id": w.id,
            "label": w.label,
            "biggest": biggest,
            "count": len(result["tipping"]),
        }
        store.insert_alert(w.id, "tipping_point", payload)
        created.append({"kind": "tipping_point", **payload})

    if w.last_delta is not None:
        shift = result["mean_delta"] - w.last_delta
        if abs(shift) >= threshold:
            payload = {
                "subject": w.subject,
                "watchlist_id": w.id,
                "label": w.label,
                "previous_delta": w.last_delta,
                "current_delta": result["mean_delta"],
                "shift": shift,
            }
            store.insert_alert(w.id, "consensus_shift", payload)
            created.append({"kind": "consensus_shift", **payload})

    store.touch_run(w.id, result["mean_delta"])
    # GOV-04: ทุกการรันจาก watchlist ทิ้งร่องรอยใน audit log (best-effort — audit ล่มไม่หยุด loop)
    try:
        from governance.store import GovernanceStore

        gov = GovernanceStore(get_settings().postgres_url)
        gov.append_audit(
            actor="watchlist-scheduler",
            action="watchlist_check",
            run_id=f"watchlist-{w.id}",
            config_hash="-",
            detail=f"mean_delta={result['mean_delta']:.4f} alerts={len(created)}",
        )
    except Exception:
        pass
    for alert in created:
        fire_webhook(alert["kind"], alert)  # พัง = ข้าม (in-app alert บันทึกไปแล้ว)
    return created


def default_runner(subject: str, agents: int) -> dict:
    """รันกลไกจริง (ไม่มี LLM = $0 — BudgetGuard ไม่มีอะไรให้หัก แต่ cap ยังคุม n)"""
    from api.app import EVENT, RUMOR
    from simulation.engine import Message
    from simulation.experiment import run_whatif
    from simulation.persona import PersonaFactory
    from simulation.tipping import tipping_from_run

    settings = get_settings()
    n = min(agents, settings.max_agents_per_run)
    estimate, outcomes = run_whatif(
        lambda s: PersonaFactory().sample(n, seed=s, max_agents=n),
        seeds=[settings.default_seed + i for i in range(3)],
        rounds=20,
        base_messages=[Message("rumor", "rumor", RUMOR, 1, "public_feed")],
        event=Message("official", "correction", EVENT, 8, "public_feed", counters="rumor"),
        target_msg_id="rumor",
    )
    tipping = [tp.to_dict() for tp in tipping_from_run(outcomes[0].variant, "rumor")]
    return {"mean_delta": estimate.mean_delta, "tipping": tipping}
