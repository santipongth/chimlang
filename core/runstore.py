"""Run store (P6-M2) — เก็บผลรันถาวร: หน้า History / Run detail / Replay

ตารางเป็น **operational** (ลบ run ได้ — ต่างจาก audit/registry ที่ append-only)
แต่ทุกการสร้าง/ลบต้อง append audit log ที่ชั้น API (GOV-04) และทุก run ที่สร้างผ่าน
POST /runs ต้อง register prediction ≥ 1 (กฎเหล็กข้อ 3 — UI run คือ simulation run จริง)
"""

import json
from datetime import UTC, datetime

import psycopg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sim_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    engine TEXT NOT NULL,
    subject TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT 'ทั่วไป',
    agents INT NOT NULL,
    rounds INT NOT NULL DEFAULT 0,
    seed BIGINT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'running' CHECK (
        status IN ('queued', 'running', 'complete', 'error', 'canceled')
    ),
    job_id TEXT NOT NULL DEFAULT '',
    queued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    progress INT NOT NULL DEFAULT 0,
    progress_message TEXT NOT NULL DEFAULT '',
    payload JSONB,
    error TEXT
);
CREATE TABLE IF NOT EXISTS debate_posts (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES sim_runs(run_id) ON DELETE CASCADE,
    round_no INT NOT NULL,
    agent_idx INT NOT NULL,
    segment TEXT NOT NULL,
    content TEXT NOT NULL,
    stance DOUBLE PRECISION NOT NULL,
    sentiment DOUBLE PRECISION NOT NULL,
    failed BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS debate_posts_run ON debate_posts (run_id, round_no, agent_idx);
"""


class RunStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            conn.execute("ALTER TABLE sim_runs DROP CONSTRAINT IF EXISTS sim_runs_status_check")
            conn.execute(
                "ALTER TABLE sim_runs ADD CONSTRAINT sim_runs_status_check "
                "CHECK (status IN ('queued', 'running', 'complete', 'error', 'canceled'))"
            )
            conn.execute(
                "ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS job_id TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS queued_at "
                "TIMESTAMPTZ NOT NULL DEFAULT now()"
            )
            conn.execute("ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ")
            conn.execute("ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ")
            conn.execute(
                "ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS progress INT NOT NULL DEFAULT 0"
            )
            conn.execute(
                "ALTER TABLE sim_runs ADD COLUMN IF NOT EXISTS progress_message "
                "TEXT NOT NULL DEFAULT ''"
            )

    def create(
        self,
        *,
        run_id: str,
        engine: str,
        subject: str,
        domain: str,
        agents: int,
        rounds: int,
        seed: int,
        config: dict,
        status: str = "running",
        job_id: str = "",
        progress_message: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sim_runs "
                "(run_id, engine, subject, domain, agents, rounds, seed, config, status, "
                "job_id, started_at, progress, progress_message) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "CASE WHEN %s = 'running' THEN now() ELSE NULL END, %s, %s)",
                (
                    run_id,
                    engine,
                    subject,
                    domain,
                    agents,
                    rounds,
                    seed,
                    json.dumps(config, ensure_ascii=False),
                    status,
                    job_id,
                    status,
                    5 if status == "running" else 0,
                    progress_message,
                ),
            )

    def attach_job(self, run_id: str, job_id: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE sim_runs SET job_id = %s WHERE run_id = %s", (job_id, run_id))

    def mark_running(self, run_id: str, message: str = "running") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'running', started_at = COALESCE(started_at, now()), "
                "progress = GREATEST(progress, 5), progress_message = %s WHERE run_id = %s",
                (message, run_id),
            )

    def update_progress(self, run_id: str, progress: int, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET progress = %s, progress_message = %s WHERE run_id = %s "
                "AND status IN ('queued', 'running')",
                (max(0, min(99, progress)), message[:200], run_id),
            )

    def finish(self, run_id: str, payload: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'complete', payload = %s, progress = 100, "
                "progress_message = 'complete', finished_at = now() WHERE run_id = %s",
                (json.dumps(payload, ensure_ascii=False), run_id),
            )

    def update_payload(self, run_id: str, payload: dict, message: str = "updated") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET payload = %s, progress_message = %s WHERE run_id = %s",
                (json.dumps(payload, ensure_ascii=False), message[:200], run_id),
            )

    def fail(self, run_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'error', error = %s, progress_message = 'error', "
                "finished_at = now() WHERE run_id = %s",
                (error[:500], run_id),
            )

    def cancel(self, run_id: str, reason: str = "canceled") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'canceled', error = %s, "
                "progress_message = 'canceled', "
                "finished_at = now() WHERE run_id = %s AND status IN ('queued', 'running')",
                (reason[:500], run_id),
            )

    def add_posts(self, run_id: str, posts: list[dict]) -> None:
        if not posts:
            return
        with self._conn() as conn:
            conn.cursor().executemany(
                "INSERT INTO debate_posts "
                "(run_id, round_no, agent_idx, segment, content, stance, sentiment, failed) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        run_id,
                        p["round_no"],
                        p["agent_idx"],
                        p["segment"],
                        p["content"],
                        p["stance"],
                        p["sentiment"],
                        p.get("failed", False),
                    )
                    for p in posts
                ],
            )

    def list_runs(
        self,
        *,
        search: str = "",
        engine: str = "",
        status: str = "",
        limit: int = 50,
    ) -> list[dict]:
        q = (
            "SELECT run_id, created_at, engine, subject, domain, agents, rounds, status, "
            "job_id, queued_at, started_at, finished_at, progress, progress_message "
            "FROM sim_runs WHERE true"
        )
        params: list = []
        if search.strip():
            q += " AND subject ILIKE %s"
            params.append(f"%{search.strip()}%")
        if engine:
            q += " AND engine = %s"
            params.append(engine)
        if status:
            q += " AND status = %s"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(q, params).fetchall()
        return [
            {
                "run_id": r[0],
                "created_at": r[1].isoformat(),
                "engine": r[2],
                "subject": r[3],
                "domain": r[4],
                "agents": r[5],
                "rounds": r[6],
                "status": r[7],
                "job_id": r[8],
                "queued_at": r[9].isoformat() if r[9] else None,
                "started_at": r[10].isoformat() if r[10] else None,
                "finished_at": r[11].isoformat() if r[11] else None,
                "progress": r[12],
                "progress_message": r[13],
            }
            for r in rows
        ]

    def get(self, run_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT run_id, created_at, engine, subject, domain, agents, rounds, seed, "
                "config, status, payload, error, job_id, queued_at, started_at, finished_at, "
                "progress, progress_message FROM sim_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ run {run_id}")
            posts = conn.execute(
                "SELECT round_no, agent_idx, segment, content, stance, sentiment, failed "
                "FROM debate_posts WHERE run_id = %s ORDER BY round_no, agent_idx",
                (run_id,),
            ).fetchall()
        return {
            "run_id": row[0],
            "created_at": row[1].isoformat(),
            "engine": row[2],
            "subject": row[3],
            "domain": row[4],
            "agents": row[5],
            "rounds": row[6],
            "seed": row[7],
            "config": row[8],
            "status": row[9],
            "payload": row[10],
            "error": row[11],
            "job_id": row[12],
            "queued_at": row[13].isoformat() if row[13] else None,
            "started_at": row[14].isoformat() if row[14] else None,
            "finished_at": row[15].isoformat() if row[15] else None,
            "progress": row[16],
            "progress_message": row[17],
            "posts": [
                {
                    "round_no": p[0],
                    "agent_idx": p[1],
                    "segment": p[2],
                    "content": p[3],
                    "stance": p[4],
                    "sentiment": p[5],
                    "failed": p[6],
                }
                for p in posts
            ],
        }

    def find_by_job(self, job_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT run_id, status, progress, progress_message, error "
                "FROM sim_runs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "status": row[1],
            "progress": row[2],
            "progress_message": row[3],
            "error": row[4],
        }

    def metrics(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, count(*), avg(EXTRACT(EPOCH FROM (finished_at - started_at))) "
                "FROM sim_runs GROUP BY status"
            ).fetchall()
            timing = conn.execute(
                "SELECT "
                "avg(EXTRACT(EPOCH FROM (started_at - queued_at))) "
                "FILTER (WHERE started_at IS NOT NULL), "
                "avg(EXTRACT(EPOCH FROM (finished_at - started_at))) "
                "FILTER (WHERE finished_at IS NOT NULL) "
                "FROM sim_runs"
            ).fetchone()
            failures = conn.execute(
                "SELECT count(*) FROM sim_runs WHERE status = 'error' "
                "AND created_at > now() - interval '24 hours'"
            ).fetchone()[0]
            try:
                source_rows = conn.execute(
                    "SELECT status, count(*) FROM run_sources GROUP BY status"
                ).fetchall()
            except Exception:
                source_rows = []
            try:
                news_rows = conn.execute(
                    "SELECT status, count(*) FROM news_items GROUP BY status"
                ).fetchall()
            except Exception:
                news_rows = []
            recent_rows = conn.execute(
                "SELECT run_id, created_at, engine, status, progress, progress_message "
                "FROM sim_runs ORDER BY created_at DESC LIMIT 12"
            ).fetchall()
            hourly_rows = conn.execute(
                "SELECT date_trunc('hour', created_at) AS h, status, count(*) "
                "FROM sim_runs WHERE created_at > now() - interval '24 hours' "
                "GROUP BY h, status ORDER BY h"
            ).fetchall()
        return {
            "by_status": {
                r[0]: {"count": int(r[1]), "avg_runtime_s": float(r[2] or 0)} for r in rows
            },
            "avg_queue_wait_s": float(timing[0] or 0),
            "avg_runtime_s": float(timing[1] or 0),
            "errors_24h": int(failures),
            "sources_by_status": {r[0]: int(r[1]) for r in source_rows},
            "news_by_status": {r[0]: int(r[1]) for r in news_rows},
            "recent": [
                {
                    "run_id": r[0],
                    "created_at": r[1].isoformat(),
                    "engine": r[2],
                    "status": r[3],
                    "progress": r[4],
                    "progress_message": r[5],
                }
                for r in recent_rows
            ],
            "runs_24h": [
                {"hour": r[0].isoformat(), "status": r[1], "count": int(r[2])} for r in hourly_rows
            ],
        }

    def delete(self, run_id: str) -> None:
        """ลบ run (operational) — audit การลบเป็นหน้าที่ชั้น API; registry/audit เดิมคงอยู่"""
        with self._conn() as conn:
            conn.execute("DELETE FROM sim_runs WHERE run_id = %s", (run_id,))


def new_run_id(engine: str) -> str:
    return f"{engine}-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}"
