from datetime import date
from pathlib import Path

import pytest

from core.run_context import (
    ExternalRetrievalBlockedError,
    RunContext,
    ensure_external_retrieval_allowed,
)
from trust.hindcast import RetrievalFilter, extract_doc_date

CUTOFF = date(2022, 5, 20)


def test_extract_date_from_filename():
    assert extract_doc_date("2022-05-15-โพลโค้งสุดท้าย.md") == date(2022, 5, 15)
    assert extract_doc_date("บทความไม่มีวันที่.md") is None
    assert extract_doc_date("2022-13-99-วันที่เพี้ยน.md") is None  # วันที่ invalid = None


def test_filter_boundaries():
    f = RetrievalFilter(cutoff=CUTOFF)
    assert f.allows(date(2022, 5, 19)) is True
    assert f.allows(CUTOFF) is True  # วัน cutoff เองยังอนุญาต
    assert f.allows(date(2022, 5, 21)) is False  # หลัง cutoff 1 วัน = block
    assert f.allows(None) is False  # fail-closed: ไม่มีวันที่ = block


def test_split_paths_fail_closed():
    f = RetrievalFilter(cutoff=CUTOFF)
    paths = [
        Path("2022-05-01-ก่อน.md"),
        Path("2022-05-22-หลัง.md"),
        Path("ไม่มีวันที่.md"),
    ]
    allowed, blocked = f.split_paths(paths)
    assert [p.name for p in allowed] == ["2022-05-01-ก่อน.md"]
    assert {p.name for p in blocked} == {"2022-05-22-หลัง.md", "ไม่มีวันที่.md"}


def test_hindcast_mode_blocks_external_retrieval():
    ctx = RunContext(run_id="r1", seed=42, hindcast_mode=True, cutoff_date=CUTOFF)
    with pytest.raises(ExternalRetrievalBlockedError):
        ensure_external_retrieval_allowed(ctx)


def test_normal_mode_allows_external_retrieval():
    ctx = RunContext(run_id="r1", seed=42)
    ensure_external_retrieval_allowed(ctx)  # ไม่ raise


def test_hindcast_mode_requires_cutoff():
    with pytest.raises(ValueError):
        RunContext(run_id="r1", seed=42, hindcast_mode=True)
