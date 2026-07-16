"""Honest Phase 8 benchmark metrics with Thai-first fixtures.

The functions return raw metrics and sample sizes.  They intentionally do not
invent a pass threshold: changing product gates requires a reviewed benchmark
decision, not a convenient number in implementation code.
"""

from __future__ import annotations

import math


def retrieval_metrics(cases: list[dict], *, k: int = 5) -> dict:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    for case in cases:
        relevant = {str(item) for item in case.get("relevant_ids", [])}
        returned = [str(item) for item in case.get("returned_ids", [])[:k]]
        recalls.append(len(relevant & set(returned)) / len(relevant) if relevant else 0.0)
        rank = next((i for i, item in enumerate(returned, start=1) if item in relevant), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    n = len(cases)
    return {
        "sample_size": n,
        "k": k,
        "recall_at_k": round(sum(recalls) / n, 6) if n else 0.0,
        "mrr_at_k": round(sum(reciprocal_ranks) / n, 6) if n else 0.0,
        "per_case_recall": [round(value, 6) for value in recalls],
    }


def evidence_relevance_metrics(items: list[dict]) -> dict:
    """Score citation validity and human-labelled relevance separately."""

    total_refs = valid_refs = relevant_refs = unsupported = 0
    for item in items:
        known = {str(ref) for ref in item.get("available_evidence_ids", [])}
        relevant = {str(ref) for ref in item.get("relevant_evidence_ids", [])}
        refs = [str(ref) for ref in item.get("evidence_refs", [])]
        total_refs += len(refs)
        valid_refs += sum(ref in known for ref in refs)
        relevant_refs += sum(ref in relevant for ref in refs)
        unsupported += int(bool(item.get("requires_evidence")) and not refs)
    return {
        "sample_size": len(items),
        "citation_count": total_refs,
        "citation_validity": round(valid_refs / total_refs, 6) if total_refs else 0.0,
        "evidence_precision": round(relevant_refs / total_refs, 6) if total_refs else 0.0,
        "unsupported_claims": unsupported,
    }


def subgroup_fidelity_metrics(target: dict[str, float], observed: dict[str, float]) -> dict:
    groups = sorted(set(target) | set(observed))
    gaps = {group: float(observed.get(group, 0)) - float(target.get(group, 0)) for group in groups}
    absolute = [abs(gap) for gap in gaps.values()]
    return {
        "sample_size": len(groups),
        "mean_absolute_error": round(sum(absolute) / len(absolute), 6) if absolute else 0.0,
        "max_absolute_error": round(max(absolute), 6) if absolute else 0.0,
        "gaps": {key: round(value, 6) for key, value in gaps.items()},
        "target_total": round(sum(float(v) for v in target.values()), 6),
        "observed_total": round(sum(float(v) for v in observed.values()), 6),
    }


def social_desirability_metrics(cases: list[dict]) -> dict:
    """Measure whether simulated public/private gaps have the labelled direction."""

    matches = 0
    gaps: list[float] = []
    for case in cases:
        gap = float(case["public_stance"]) - float(case["private_stance"])
        gaps.append(gap)
        expected = int(case.get("expected_gap_sign", 0))
        observed = 1 if gap > 0 else -1 if gap < 0 else 0
        matches += int(observed == expected)
    n = len(cases)
    return {
        "sample_size": n,
        "direction_accuracy": round(matches / n, 6) if n else 0.0,
        "mean_signed_gap": round(sum(gaps) / n, 6) if n else 0.0,
        "mean_absolute_gap": round(sum(abs(gap) for gap in gaps) / n, 6) if n else 0.0,
        "raw_gaps": [round(gap, 6) for gap in gaps],
    }


def future_calibration_metrics(predictions: list[dict], *, bins: int = 5) -> dict:
    usable = [
        (float(item["probability"]), int(bool(item["outcome"])), float(item.get("baseline", 0.5)))
        for item in predictions
        if item.get("outcome") in (True, False) and 0 <= float(item.get("probability", -1)) <= 1
    ]
    n = len(usable)
    if not n:
        return {
            "sample_size": 0,
            "brier": None,
            "baseline_brier": None,
            "brier_skill": None,
            "ece": None,
            "bins": [],
        }
    brier = sum((p - y) ** 2 for p, y, _ in usable) / n
    baseline = sum((base - y) ** 2 for _, y, base in usable) / n
    reliability = []
    ece = 0.0
    for index in range(bins):
        lo, hi = index / bins, (index + 1) / bins
        rows = [row for row in usable if lo <= row[0] <= hi if index == bins - 1 or row[0] < hi]
        if not rows:
            reliability.append({"bin": index + 1, "lo": lo, "hi": hi, "n": 0})
            continue
        mean_p = sum(row[0] for row in rows) / len(rows)
        outcome_rate = sum(row[1] for row in rows) / len(rows)
        ece += len(rows) / n * abs(mean_p - outcome_rate)
        reliability.append(
            {
                "bin": index + 1,
                "lo": lo,
                "hi": hi,
                "n": len(rows),
                "mean_probability": round(mean_p, 6),
                "outcome_rate": round(outcome_rate, 6),
            }
        )
    skill = 1 - brier / baseline if baseline > 0 else math.nan
    return {
        "sample_size": n,
        "brier": round(brier, 6),
        "baseline_brier": round(baseline, 6),
        "brier_skill": round(skill, 6) if math.isfinite(skill) else None,
        "ece": round(ece, 6),
        "bins": reliability,
    }
