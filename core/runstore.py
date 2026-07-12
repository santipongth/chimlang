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
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'complete', 'error')),
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
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sim_runs "
                "(run_id, engine, subject, domain, agents, rounds, seed, config) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    engine,
                    subject,
                    domain,
                    agents,
                    rounds,
                    seed,
                    json.dumps(config, ensure_ascii=False),
                ),
            )

    def finish(self, run_id: str, payload: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'complete', payload = %s WHERE run_id = %s",
                (json.dumps(payload, ensure_ascii=False), run_id),
            )

    def fail(self, run_id: str, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE sim_runs SET status = 'error', error = %s WHERE run_id = %s",
                (error[:500], run_id),
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
            "SELECT run_id, created_at, engine, subject, domain, agents, rounds, status "
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
            }
            for r in rows
        ]

    def get(self, run_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT run_id, created_at, engine, subject, domain, agents, rounds, seed, "
                "config, status, payload, error FROM sim_runs WHERE run_id = %s",
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

    def delete(self, run_id: str) -> None:
        """ลบ run (operational) — audit การลบเป็นหน้าที่ชั้น API; registry/audit เดิมคงอยู่"""
        with self._conn() as conn:
            conn.execute("DELETE FROM sim_runs WHERE run_id = %s", (run_id,))


def new_run_id(engine: str) -> str:
    return f"{engine}-{datetime.now(UTC):%Y%m%d-%H%M%S-%f}"
