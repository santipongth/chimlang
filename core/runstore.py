"""Run store (P6-M2) — เก็บผลรันถาวร: หน้า History / Run detail / Replay

ตารางเป็น **operational** (ลบ run ได้ — ต่างจาก audit/registry ที่ append-only)
แต่ทุกการสร้าง/ลบต้อง append audit log ที่ชั้น API (GOV-04) และทุก run ที่สร้างผ่าน
POST /runs ต้อง register SimulationFinding หรือ Prediction อย่างน้อย 1 รายการ
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

from core.db import connection, require_schema
from core.run_events import publish_event, safe_event_message, safe_event_payload

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
    error TEXT,
    parent_run_id TEXT NOT NULL DEFAULT ''
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
    failed BOOLEAN NOT NULL DEFAULT false,
    failure_reason TEXT NOT NULL DEFAULT '',
    parser_mode TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS debate_posts_run ON debate_posts (run_id, round_no, agent_idx);
CREATE TABLE IF NOT EXISTS run_events (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    message TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS run_events_run ON run_events (run_id, created_at);
"""


class RunStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return connection(self._dsn)

    def setup(self) -> None:
        """Compatibility shim: read-only readiness check; never executes DDL."""
        require_schema(self._dsn)

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
        parent_run_id: str = "",
        idempotency_key: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sim_runs "
                "(run_id, engine, subject, domain, agents, rounds, seed, config, status, "
                "job_id, started_at, progress, progress_message, parent_run_id, "
                "heartbeat_at, idempotency_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "CASE WHEN %s = 'running' THEN now() ELSE NULL END, %s, %s, %s, "
                "CASE WHEN %s = 'running' THEN now() ELSE NULL END, %s)",
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
                    parent_run_id,
                    status,
                    idempotency_key,
                ),
            )
        self.add_event(
            run_id,
            "created",
            stage="queue" if status == "queued" else "start",
            progress=0 if status == "queued" else 5,
            message=status,
            payload={"engine": engine, "status": status, "parent_run_id": parent_run_id},
        )

    def attach_job(self, run_id: str, job_id: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE sim_runs SET job_id = %s WHERE run_id = %s", (job_id, run_id))
        self.add_event(
            run_id,
            "job_attached",
            stage="queue",
            message=job_id,
            payload={"job_id": job_id},
        )

    def mark_running(self, run_id: str, message: str = "running") -> bool:
        with self._conn() as conn:
            updated = conn.execute(
                "UPDATE sim_runs SET status = 'running', started_at = COALESCE(started_at, now()), "
                "progress = GREATEST(progress, 5), progress_message = %s, "
                "heartbeat_at = now(), attempt = attempt + 1 "
                "WHERE run_id = %s AND status = 'queued' RETURNING run_id",
                (message, run_id),
            ).fetchone()
            if updated is None:
                return False
        self.add_event(run_id, "running", stage="start", progress=5, message=message)
        return True

    def update_progress(self, run_id: str, progress: int, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET progress = %s, progress_message = %s, heartbeat_at = now() "
                "WHERE run_id = %s "
                "AND status IN ('queued', 'running')",
                (max(0, min(99, progress)), message[:200], run_id),
            )
        self.add_event(
            run_id,
            "progress",
            stage=message[:80],
            progress=max(0, min(99, progress)),
            message=message,
        )

    def heartbeat(self, run_id: str, message: str = "worker heartbeat") -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "UPDATE sim_runs SET heartbeat_at = now(), progress_message = %s "
                "WHERE run_id = %s AND status = 'running' RETURNING run_id",
                (message[:200], run_id),
            ).fetchone()
        return row is not None

    def finish(self, run_id: str, payload: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'complete', payload = %s, progress = 100, "
                "progress_message = 'complete', finished_at = now(), heartbeat_at = now() "
                "WHERE run_id = %s",
                (json.dumps(payload, ensure_ascii=False), run_id),
            )
        self.add_event(
            run_id,
            "completed",
            stage="complete",
            progress=100,
            call_status="success",
            cost_usd=float(payload.get("cost_usd", 0) or 0),
            message="complete",
        )

    def update_payload(self, run_id: str, payload: dict, message: str = "updated") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET payload = %s, progress_message = %s WHERE run_id = %s",
                (json.dumps(payload, ensure_ascii=False), message[:200], run_id),
            )
        self.add_event(run_id, "payload_updated", stage="repair", message=message)

    def fail(self, run_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'error', error = %s, progress_message = 'error', "
                "finished_at = now() WHERE run_id = %s",
                (safe_event_message(error), run_id),
            )
        self.add_event(
            run_id,
            "failed",
            stage="failed",
            call_status="failed",
            message=error,
        )

    def cancel(self, run_id: str, reason: str = "canceled") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'canceled', error = %s, "
                "progress_message = 'canceled', "
                "finished_at = now() WHERE run_id = %s AND status IN ('queued', 'running')",
                (reason[:500], run_id),
            )
        self.add_event(run_id, "canceled", stage="canceled", message=reason)

    def add_posts(self, run_id: str, posts: list[dict]) -> None:
        if not posts:
            return
        with self._conn() as conn:
            conn.cursor().executemany(
                "INSERT INTO debate_posts "
                "(run_id, round_no, agent_idx, segment, content, stance, sentiment, "
                "failed, failure_reason, parser_mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
                        p.get("failure_reason", ""),
                        p.get("parser_mode", ""),
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
                "progress, progress_message, parent_run_id, heartbeat_at, attempt "
                "FROM sim_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ run {run_id}")
            posts = conn.execute(
                "SELECT round_no, agent_idx, segment, content, stance, sentiment, failed, "
                "COALESCE(failure_reason, ''), COALESCE(parser_mode, '') "
                "FROM debate_posts WHERE run_id = %s ORDER BY round_no, agent_idx",
                (run_id,),
            ).fetchall()
            events = conn.execute(
                "SELECT id, created_at, event_type, actor, message, payload, stage, progress, "
                "call_status, cost_usd "
                "FROM run_events WHERE run_id = %s ORDER BY created_at, id",
                (run_id,),
            ).fetchall()
            revisions = conn.execute(
                "SELECT id, created_at, kind, synthesis, metrics, model_version, parser_mode, "
                "cost_usd FROM run_synthesis_revisions WHERE run_id = %s ORDER BY id",
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
            "parent_run_id": row[18],
            "heartbeat_at": row[19].isoformat() if row[19] else None,
            "attempt": row[20],
            "posts": [
                {
                    "round_no": p[0],
                    "agent_idx": p[1],
                    "segment": p[2],
                    "content": p[3],
                    "stance": p[4],
                    "sentiment": p[5],
                    "failed": p[6],
                    "failure_reason": p[7],
                    "parser_mode": p[8],
                }
                for p in posts
            ],
            "events": [
                {
                    "id": e[0],
                    "created_at": e[1].isoformat(),
                    "event_type": e[2],
                    "actor": e[3],
                    "message": e[4],
                    "payload": e[5],
                    "stage": e[6],
                    "progress": e[7],
                    "call_status": e[8],
                    "cost_usd": float(e[9]) if e[9] is not None else None,
                }
                for e in events
            ],
            "synthesis_revisions": [
                {
                    "id": r[0],
                    "created_at": r[1].isoformat(),
                    "kind": r[2],
                    "synthesis": r[3],
                    "metrics": r[4],
                    "model_version": r[5],
                    "parser_mode": r[6],
                    "cost_usd": float(r[7]),
                }
                for r in revisions
            ],
        }

    def add_event(
        self,
        run_id: str,
        event_type: str,
        *,
        actor: str = "system",
        message: str = "",
        payload: dict | None = None,
        stage: str = "",
        progress: int | None = None,
        call_status: str = "",
        cost_usd: float | None = None,
    ) -> int:
        safe_message = safe_event_message(message)
        safe_payload = safe_event_payload(payload or {})
        with self._conn() as conn:
            event_id = conn.execute(
                "INSERT INTO run_events (run_id, event_type, actor, message, payload, stage, "
                "progress, call_status, cost_usd) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id",
                (
                    run_id,
                    event_type[:80],
                    actor[:120],
                    safe_message,
                    json.dumps(safe_payload, ensure_ascii=False),
                    stage[:80],
                    None if progress is None else max(0, min(100, progress)),
                    call_status[:40],
                    cost_usd,
                ),
            ).fetchone()[0]
        publish_event(run_id, int(event_id))
        return int(event_id)

    def events_after(self, run_id: str, after_id: int, *, limit: int = 200) -> list[dict]:
        with self._conn() as conn:
            exists = conn.execute("SELECT 1 FROM sim_runs WHERE run_id = %s", (run_id,)).fetchone()
            if exists is None:
                raise ValueError(f"ไม่พบ run {run_id}")
            rows = conn.execute(
                "SELECT id, created_at, event_type, stage, progress, call_status, cost_usd, "
                "message, payload FROM run_events WHERE run_id = %s AND id > %s "
                "ORDER BY id LIMIT %s",
                (run_id, max(0, after_id), max(1, min(1000, limit))),
            ).fetchall()
        return [
            {
                "id": r[0],
                "created_at": r[1].isoformat(),
                "event_type": r[2],
                "stage": r[3],
                "progress": r[4],
                "call_status": r[5],
                "cost_usd": float(r[6]) if r[6] is not None else None,
                "message": r[7],
                "payload": r[8],
            }
            for r in rows
        ]

    def add_synthesis_revision(
        self,
        run_id: str,
        *,
        kind: str,
        synthesis: dict,
        metrics: dict | None = None,
        model_version: str = "",
        parser_mode: str = "",
        cost_usd: float = 0,
    ) -> int:
        if kind not in {"analyst", "mechanical"}:
            raise ValueError("kind ต้องเป็น analyst หรือ mechanical")
        with self._conn() as conn:
            revision_id = conn.execute(
                "INSERT INTO run_synthesis_revisions "
                "(run_id, kind, synthesis, metrics, model_version, parser_mode, cost_usd) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    run_id,
                    kind,
                    json.dumps(synthesis, ensure_ascii=False),
                    json.dumps(metrics or {}, ensure_ascii=False),
                    model_version,
                    parser_mode,
                    max(0.0, cost_usd),
                ),
            ).fetchone()[0]
        self.add_event(
            run_id,
            "synthesis_revision",
            stage="synthesis",
            call_status="success",
            cost_usd=max(0.0, cost_usd),
            message=f"{kind} revision {revision_id}",
        )
        return int(revision_id)

    def mark_stale(self, *, running_after_s: int = 180, queued_after_s: int = 300) -> list[str]:
        """Fail stale jobs with an explicit, inspectable reason."""
        reason = "worker heartbeat ขาดหายเกินกำหนด"
        with self._conn() as conn:
            rows = conn.execute(
                "UPDATE sim_runs SET status = 'error', error = %s, progress_message = 'stale', "
                "finished_at = now() WHERE (status = 'running' AND "
                "COALESCE(heartbeat_at, started_at, queued_at) "
                "< now() - (%s || ' seconds')::interval) "
                "OR (status = 'queued' AND queued_at < now() - (%s || ' seconds')::interval) "
                "RETURNING run_id",
                (reason, running_after_s, queued_after_s),
            ).fetchall()
        run_ids = [r[0] for r in rows]
        for run_id in run_ids:
            self.add_event(
                run_id,
                "stale",
                stage="stale",
                call_status="failed",
                message=reason,
            )
        return run_ids

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

    def children(self, parent_run_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT run_id, engine, seed, status, payload, error, agents, rounds "
                "FROM sim_runs WHERE parent_run_id = %s ORDER BY created_at, id",
                (parent_run_id,),
            ).fetchall()
        return [
            {
                "run_id": r[0],
                "engine": r[1],
                "seed": r[2],
                "status": r[3],
                "payload": r[4],
                "error": r[5],
                "agents": r[6],
                "rounds": r[7],
            }
            for r in rows
        ]

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
    # UUID suffix prevents collisions when concurrent requests share a clock tick.
    return f"{engine}-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}-{uuid4().hex[:8]}"
