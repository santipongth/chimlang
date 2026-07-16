"""Run the offline Thai M5 benchmark suite without any provider calls."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from simulation.debate_protocol import verify_moves
from simulation.reflection import ReflectionPolicy, reflection_benchmark
from simulation.sources import _bm25_scores
from trust.benchmarks import (
    evidence_relevance_metrics,
    future_calibration_metrics,
    retrieval_metrics,
    social_desirability_metrics,
    subgroup_fidelity_metrics,
)

FIXTURE = (
    Path(__file__).resolve().parents[1] / "data" / "samples" / "benchmarks" / "phase8-thai.json"
)


def run(path: Path = FIXTURE) -> dict:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    ranked_cases = []
    for case in fixture["retrieval"]:
        rows = [
            (index, doc_id, 0, content)
            for index, (doc_id, content) in enumerate(case["documents"].items(), start=1)
        ]
        scores = _bm25_scores(rows, case["query"])
        id_by_index = {row[0]: row[1] for row in rows}
        returned = [id_by_index[index] for index in sorted(scores, key=lambda i: -scores[i])]
        ranked_cases.append({"relevant_ids": case["relevant_ids"], "returned_ids": returned})
    reflection = fixture["reflection"]

    def moves(items: list[dict]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                **{**item, "evidence_refs": tuple(item.get("evidence_refs", []))},
                failed=False,
                sentiment=0.0,
            )
            for item in items
        ]

    before = verify_moves(
        moves(reflection["before_moves"]),
        evidence_ids=set(reflection["available_evidence_ids"]),
    )
    after = verify_moves(
        moves(reflection["after_moves"]),
        evidence_ids=set(reflection["available_evidence_ids"]),
    )
    return {
        "fixture": path.name,
        "language": "th",
        "retrieval": retrieval_metrics(ranked_cases),
        "evidence": evidence_relevance_metrics(fixture["evidence"]),
        "subgroup_fidelity": subgroup_fidelity_metrics(
            fixture["subgroup"]["target"], fixture["subgroup"]["observed"]
        ),
        "social_desirability": social_desirability_metrics(fixture["social_desirability"]),
        "future_calibration": future_calibration_metrics(fixture["future_calibration"]),
        "reflection_smoke": reflection_benchmark(
            before,
            after,
            calls=int(reflection["calls"]),
            policy=ReflectionPolicy(),
        ),
        "note": "รายงานตัวเลขดิบ ไม่มีการตั้ง pass threshold ย้อนหลัง",
    }


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
