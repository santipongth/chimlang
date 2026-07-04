"""Retrieval filter — block ทุกเอกสารที่ลงวันที่หลัง cutoff (TRUST-03)

fail-closed: เอกสารที่อ่านวันที่ไม่ได้ = block เสมอ (สงสัยไว้ก่อน)
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def extract_doc_date(name: str) -> date | None:
    """อ่านวันที่จากชื่อไฟล์รูปแบบ YYYY-MM-DD-หัวข้อ — อ่านไม่ได้คืน None (จะถูก block)"""
    m = _DATE_RE.search(name)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


@dataclass(frozen=True)
class RetrievalFilter:
    """อนุญาตเฉพาะเอกสารที่มีวันที่ และวันที่ ≤ cutoff"""

    cutoff: date

    def allows(self, doc_date: date | None) -> bool:
        return doc_date is not None and doc_date <= self.cutoff

    def split_paths(self, paths: list[Path]) -> tuple[list[Path], list[Path]]:
        """แยกเป็น (allowed, blocked) — blocked รวมไฟล์ไม่มีวันที่ (fail-closed)"""
        allowed: list[Path] = []
        blocked: list[Path] = []
        for p in paths:
            (allowed if self.allows(extract_doc_date(p.name)) else blocked).append(p)
        return allowed, blocked
