"""Persistent event-sourced rehearsal sessions (P9-M3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from core.db import connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rehearsal_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    title TEXT NOT NULL,
    scenario TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active','paused','complete','error')),
    seed INT NOT NULL,
    netizens INT NOT NULL,
    max_turns INT NOT NULL,
    reactions_per_turn INT NOT NULL,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rehearsal_events (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES rehearsal_sessions(session_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'session_created','question','answer','decision',
            'paused','resumed','scorecard','error'
        )
    ),
    turn_no INT,
    actor TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS rehearsal_events_session ON rehearsal_events(session_id, id);
CREATE TABLE IF NOT EXISTS rehearsal_operation_leases (
    session_id TEXT PRIMARY KEY REFERENCES rehearsal_sessions(session_id),
    token TEXT NOT NULL,
    operation TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '10 minutes'
);
DROP TRIGGER IF EXISTS rehearsal_events_append_only ON rehearsal_events;
CREATE TRIGGER rehearsal_events_append_only
    BEFORE UPDATE OR DELETE ON rehearsal_events
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""


class RehearsalStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    @staticmethod
    def new_session_id() -> str:
        return f"rehearsal-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"

    def create(
        self,
        *,
        title: str,
        scenario: str,
        seed: int,
        netizens: int,
        max_turns: int,
        reactions_per_turn: int,
        actor: str,
        session_id: str = "",
    ) -> dict:
        session_id = session_id or self.new_session_id()
        with connection(self._dsn) as conn:
            conn.execute(
                "INSERT INTO rehearsal_sessions "
                "(session_id,title,scenario,status,seed,netizens,max_turns,"
                "reactions_per_turn,created_by) "
                "VALUES (%s,%s,%s,'active',%s,%s,%s,%s,%s)",
                (
                    session_id,
                    title.strip()[:200],
                    scenario.strip()[:20_000],
                    seed,
                    netizens,
                    max_turns,
                    reactions_per_turn,
                    actor[:160],
                ),
            )
            conn.execute(
                "INSERT INTO rehearsal_events (session_id,event_type,actor,payload) "
                "VALUES (%s,'session_created',%s,%s::jsonb)",
                (
                    session_id,
                    actor[:160],
                    json.dumps(
                        {
                            "seed": seed,
                            "netizens": netizens,
                            "max_turns": max_turns,
                            "reactions_per_turn": reactions_per_turn,
                        }
                    ),
                ),
            )
        return self.get(session_id)

    def list(self, *, limit: int = 50) -> list[dict]:
        with connection(self._dsn) as conn:
            rows = conn.execute(
                "SELECT session_id,created_at,updated_at,title,status,cost_usd "
                "FROM rehearsal_sessions WHERE created_by <> 'pytest' "
                "AND title NOT LIKE 'pytest %%' ORDER BY updated_at DESC LIMIT %s",
                (max(1, min(200, limit)),),
            ).fetchall()
        return [
            {
                "session_id": row[0],
                "created_at": row[1].isoformat(),
                "updated_at": row[2].isoformat(),
                "title": row[3],
                "status": row[4],
                "cost_usd": float(row[5]),
            }
            for row in rows
        ]

    def get(self, session_id: str) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT session_id,created_at,updated_at,title,scenario,status,seed,netizens,"
                "max_turns,reactions_per_turn,cost_usd,created_by FROM rehearsal_sessions "
                "WHERE session_id = %s",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ rehearsal {session_id}")
            events = conn.execute(
                "SELECT id,created_at,event_type,turn_no,actor,payload FROM rehearsal_events "
                "WHERE session_id = %s ORDER BY id",
                (session_id,),
            ).fetchall()
        event_list = [
            {
                "id": item[0],
                "created_at": item[1].isoformat(),
                "event_type": item[2],
                "turn_no": item[3],
                "actor": item[4],
                "payload": item[5],
            }
            for item in events
        ]
        questions = {
            item["turn_no"]: item for item in event_list if item["event_type"] == "question"
        }
        answers = {item["turn_no"]: item for item in event_list if item["event_type"] == "answer"}
        turns = []
        for turn_no, question in sorted(questions.items()):
            answer = answers.get(turn_no)
            turns.append(
                {
                    "turn_no": turn_no,
                    "journalist_id": question["payload"].get("journalist_id", ""),
                    "journalist": question["payload"].get("journalist", ""),
                    "question": question["payload"].get("question", ""),
                    "question_latency_s": question["payload"].get("latency_s", 0),
                    "answer": (answer or {}).get("payload", {}).get("answer", ""),
                    "reactions": (answer or {}).get("payload", {}).get("reactions", []),
                    "answered": answer is not None,
                }
            )
        scorecard = next(
            (item["payload"] for item in reversed(event_list) if item["event_type"] == "scorecard"),
            None,
        )
        return {
            "session_id": row[0],
            "created_at": row[1].isoformat(),
            "updated_at": row[2].isoformat(),
            "title": row[3],
            "scenario": row[4],
            "status": row[5],
            "seed": row[6],
            "netizens": row[7],
            "max_turns": row[8],
            "reactions_per_turn": row[9],
            "cost_usd": float(row[10]),
            "created_by": row[11],
            "turns": turns,
            "decisions": [item for item in event_list if item["event_type"] == "decision"],
            "scorecard": scorecard,
            "events": event_list,
        }

    def append_event(
        self,
        session_id: str,
        *,
        event_type: str,
        actor: str,
        payload: dict,
        turn_no: int | None = None,
        require_status: str | None = None,
    ) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT status FROM rehearsal_sessions WHERE session_id = %s FOR UPDATE",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"ไม่พบ rehearsal {session_id}")
            if require_status is not None and row[0] != require_status:
                raise ValueError(f"rehearsal ต้องอยู่สถานะ {require_status}")
            conn.execute(
                "INSERT INTO rehearsal_events "
                "(session_id,event_type,turn_no,actor,payload) VALUES (%s,%s,%s,%s,%s::jsonb)",
                (
                    session_id,
                    event_type,
                    turn_no,
                    actor[:160],
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.execute(
                "UPDATE rehearsal_sessions SET updated_at = now() WHERE session_id = %s",
                (session_id,),
            )
        return self.get(session_id)

    def acquire_operation(self, session_id: str, operation: str) -> str:
        token = uuid4().hex
        with connection(self._dsn) as conn:
            if not conn.execute(
                "SELECT 1 FROM rehearsal_sessions WHERE session_id=%s", (session_id,)
            ).fetchone():
                raise ValueError(f"ไม่พบ rehearsal {session_id}")
            row = conn.execute(
                "INSERT INTO rehearsal_operation_leases (session_id,token,operation) "
                "VALUES (%s,%s,%s) ON CONFLICT (session_id) DO UPDATE SET "
                "token=excluded.token, operation=excluded.operation, acquired_at=now(), "
                "expires_at=now() + interval '10 minutes' "
                "WHERE rehearsal_operation_leases.expires_at <= now() RETURNING token",
                (session_id, token, operation[:80]),
            ).fetchone()
        if row is None:
            raise ValueError("rehearsal มี operation อื่นกำลังทำงาน")
        return token

    def release_operation(self, session_id: str, token: str) -> None:
        if not token:
            return
        with connection(self._dsn) as conn:
            conn.execute(
                "DELETE FROM rehearsal_operation_leases WHERE session_id=%s AND token=%s",
                (session_id, token),
            )

    def transition(self, session_id: str, *, expected: str, target: str, actor: str) -> dict:
        event_type = {
            ("active", "paused"): "paused",
            ("paused", "active"): "resumed",
            ("active", "complete"): "scorecard",
        }.get((expected, target))
        if event_type is None:
            raise ValueError("rehearsal state transition ไม่ถูกต้อง")
        with connection(self._dsn) as conn:
            row = conn.execute(
                "UPDATE rehearsal_sessions SET status = %s, updated_at = now() "
                "WHERE session_id = %s AND status = %s RETURNING session_id",
                (target, session_id, expected),
            ).fetchone()
            if row is None:
                raise ValueError(f"rehearsal ไม่ได้อยู่สถานะ {expected}")
            if event_type != "scorecard":
                conn.execute(
                    "INSERT INTO rehearsal_events (session_id,event_type,actor) VALUES (%s,%s,%s)",
                    (session_id, event_type, actor[:160]),
                )
        return self.get(session_id)

    def finish(self, session_id: str, *, scorecard: dict, actor: str) -> dict:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "UPDATE rehearsal_sessions SET status = 'complete', updated_at = now() "
                "WHERE session_id = %s AND status = 'active' RETURNING session_id",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError("rehearsal ต้อง active ก่อนจบ")
            conn.execute(
                "INSERT INTO rehearsal_events (session_id,event_type,actor,payload) "
                "VALUES (%s,'scorecard',%s,%s::jsonb)",
                (session_id, actor[:160], json.dumps(scorecard, ensure_ascii=False)),
            )
        return self.get(session_id)

    def add_cost(self, session_id: str, amount: float) -> float:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "UPDATE rehearsal_sessions SET cost_usd = cost_usd + %s, updated_at = now() "
                "WHERE session_id = %s RETURNING cost_usd",
                (max(0.0, amount), session_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"ไม่พบ rehearsal {session_id}")
        return float(row[0])
