"""Typed debate moves, lineage validation, and integrity summaries.

The verifier is deliberately deterministic: it never calls an LLM and therefore
can be replayed from the stored debate snapshot.  An analyst judge may consume its
compact report later, but may not erase or downgrade verifier findings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class MoveType(StrEnum):
    CLAIM = "claim"
    EVIDENCE = "evidence"
    COUNTERCLAIM = "counterclaim"
    CONCESSION = "concession"
    QUESTION = "question"


MOVE_TYPES = frozenset(item.value for item in MoveType)
_NUMBER_CLAIM = re.compile(r"(?<!\w)(?:\d+(?:[.,]\d+)?\s*%|\d{2,})(?!\w)")


@dataclass(frozen=True)
class MoveLineage:
    move_id: str
    move_type: str
    parent_move_id: str = ""
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "move_id": self.move_id,
            "move_type": self.move_type,
            "parent_move_id": self.parent_move_id,
            "evidence_refs": list(self.evidence_refs),
        }


def normalize_move_type(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in MOVE_TYPES else MoveType.CLAIM.value


def normalize_evidence_refs(value: object, *, limit: int = 8) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    refs: list[str] = []
    for item in value:
        ref = str(item).strip()[:80]
        if ref and ref not in refs:
            refs.append(ref)
        if len(refs) >= limit:
            break
    return tuple(refs)


def verify_moves(posts: list, *, evidence_ids: set[str] | None = None) -> dict:
    """Verify lineage, citations, unsupported numeric claims, and contradictions.

    ``posts`` intentionally uses structural typing so this module can verify both
    live ``DebatePost`` objects and reconstructed snapshot objects without a cycle.
    """

    available_evidence = evidence_ids or set()
    usable = [post for post in posts if not getattr(post, "failed", False)]
    if usable and not any(str(getattr(post, "move_id", "")).strip() for post in usable):
        return {
            "version": 1,
            "status": "legacy_unverifiable",
            "moves_checked": 0,
            "violations": [],
            "counts": {},
            "severity": {"error": 0, "warning": 0},
            "lineage": {"nodes": [], "edges": []},
        }
    seen: dict[str, object] = {}
    violations: list[dict] = []
    edges: list[dict] = []

    def flag(post, code: str, severity: str, detail: str) -> None:
        violations.append(
            {
                "move_id": str(getattr(post, "move_id", "")),
                "code": code,
                "severity": severity,
                "detail": detail,
            }
        )

    ordered = sorted(posts, key=lambda p: (int(p.round_no), int(p.agent_idx)))
    for post in ordered:
        if getattr(post, "failed", False):
            continue
        move_id = str(getattr(post, "move_id", "")).strip()
        move_type = str(getattr(post, "move_type", "")).strip()
        parent_id = str(getattr(post, "parent_move_id", "")).strip()
        refs = tuple(getattr(post, "evidence_refs", ()) or ())

        if not move_id:
            flag(post, "missing_move_id", "error", "move ไม่มี ID")
        elif move_id in seen:
            flag(post, "duplicate_move_id", "error", "move ID ซ้ำ")
        if move_type not in MOVE_TYPES:
            flag(post, "invalid_move_type", "error", "ชนิด move ไม่อยู่ใน contract")
        if parent_id:
            parent = seen.get(parent_id)
            if parent is None:
                flag(post, "invalid_parent", "error", "parent ต้องอ้าง move ที่เกิดก่อนหน้า")
            else:
                edges.append(
                    {
                        "from": parent_id,
                        "to": move_id,
                        "relation": move_type,
                    }
                )
                if (
                    move_type == MoveType.CONCESSION
                    and float(getattr(post, "stance", 0)) * float(getattr(parent, "stance", 0))
                    < -0.25
                ):
                    flag(
                        post,
                        "concession_stance_conflict",
                        "warning",
                        "concession เปลี่ยนขั้วสวน parent อย่างมาก",
                    )
                if (
                    int(getattr(post, "agent_idx", -1)) == int(getattr(parent, "agent_idx", -2))
                    and float(getattr(post, "stance", 0)) * float(getattr(parent, "stance", 0))
                    < -0.36
                    and move_type != MoveType.CONCESSION
                ):
                    flag(
                        post,
                        "self_contradiction",
                        "warning",
                        "agent เปลี่ยนขั้วมากโดยไม่ใช้ concession",
                    )
        elif move_type in {MoveType.COUNTERCLAIM, MoveType.CONCESSION}:
            flag(post, "missing_parent", "warning", f"{move_type} ควรอ้าง parent move")

        unknown_refs = [ref for ref in refs if ref not in available_evidence]
        if unknown_refs:
            flag(post, "unknown_evidence", "error", "อ้าง evidence ID ที่ไม่มีใน snapshot")
        content = str(getattr(post, "content", ""))
        if move_type == MoveType.EVIDENCE and not refs:
            flag(post, "evidence_without_citation", "error", "evidence move ไม่มี evidence_refs")
        if _NUMBER_CLAIM.search(content) and not refs:
            flag(post, "unsupported_numeric_claim", "warning", "ข้ออ้างเชิงตัวเลขไม่มีหลักฐาน")
        if move_id and move_id not in seen:
            seen[move_id] = post

    counts: dict[str, int] = {}
    severity: dict[str, int] = {"error": 0, "warning": 0}
    for item in violations:
        counts[item["code"]] = counts.get(item["code"], 0) + 1
        severity[item["severity"]] = severity.get(item["severity"], 0) + 1
    status = "fail" if severity["error"] else "warn" if severity["warning"] else "pass"
    return {
        "version": 1,
        "status": status,
        "moves_checked": len(seen),
        "violations": violations,
        "counts": counts,
        "severity": severity,
        "lineage": {
            "nodes": [
                {
                    **MoveLineage(
                        move_id=str(getattr(post, "move_id", "")),
                        move_type=str(getattr(post, "move_type", "")),
                        parent_move_id=str(getattr(post, "parent_move_id", "")),
                        evidence_refs=tuple(getattr(post, "evidence_refs", ()) or ()),
                    ).to_dict(),
                    "round": int(post.round_no),
                    "agent_idx": int(post.agent_idx),
                    "segment": str(post.segment),
                }
                for post in ordered
                if not getattr(post, "failed", False) and getattr(post, "move_id", "")
            ],
            "edges": edges,
        },
    }


def compact_verifier_report(report: dict, *, max_violations: int = 12) -> dict:
    """Bound what the analyst judge sees; prompts never contain full hidden trails."""

    return {
        "status": report.get("status", "fail"),
        "moves_checked": int(report.get("moves_checked", 0)),
        "counts": dict(report.get("counts", {})),
        "violations": list(report.get("violations", []))[:max_violations],
    }
