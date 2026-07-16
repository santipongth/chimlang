import pytest

from scripts.production_soak import Trial, percentile, summarize


def test_percentile_interpolates_and_handles_empty_input():
    assert percentile([], 0.95) == 0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([1, 2, 3, 4], 0.95) == pytest.approx(3.85)


def test_summary_flags_failures_and_operational_coverage():
    report = summarize(
        [
            Trial(
                index=1,
                status="complete",
                total_seconds=1,
                event_count=2,
                heartbeat_seen=True,
            ),
            Trial(index=2, status="error", total_seconds=2, error="worker lost"),
        ]
    )
    assert report["requested"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["heartbeat_coverage"] == 1
    assert report["event_coverage"] == 1
    assert report["failures"][0]["error"] == "worker lost"
