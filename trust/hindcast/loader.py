"""โหลด hindcast event จากโฟลเดอร์ data/samples/hindcast/<event>/

โครงสร้าง: meta.yaml (cutoff_date, prediction_targets), before/*.md, outcome.md
- โหลดเฉพาะ before/ ผ่าน RetrievalFilter เท่านั้น
- outcome.md คือ ground truth — ห้ามโหลดเข้า context ของ agent เด็ดขาด
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from trust.hindcast.filters import RetrievalFilter, extract_doc_date


@dataclass(frozen=True)
class HindcastDoc:
    path: Path
    doc_date: date
    text: str


@dataclass(frozen=True)
class HindcastEvent:
    event_id: str
    title: str
    event_date: date
    cutoff_date: date
    prediction_targets: tuple[dict, ...]
    before_docs: tuple[HindcastDoc, ...]
    blocked_paths: tuple[Path, ...]  # ไฟล์ใน before/ ที่ถูก filter block (รายงานเพื่อ audit)


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_event(event_dir: Path | str) -> HindcastEvent:
    event_dir = Path(event_dir)
    meta = yaml.safe_load((event_dir / "meta.yaml").read_text(encoding="utf-8"))
    cutoff = _parse_date(meta["cutoff_date"])

    retrieval_filter = RetrievalFilter(cutoff=cutoff)
    before_paths = sorted((event_dir / "before").glob("*.md"))
    allowed, blocked = retrieval_filter.split_paths(before_paths)

    docs = tuple(
        HindcastDoc(
            path=p,
            doc_date=extract_doc_date(p.name),  # allowed แล้ว = มีวันที่แน่นอน
            text=p.read_text(encoding="utf-8"),
        )
        for p in allowed
    )
    return HindcastEvent(
        event_id=meta["event_id"],
        title=meta["title"],
        event_date=_parse_date(meta["event_date"]),
        cutoff_date=cutoff,
        prediction_targets=tuple(meta.get("prediction_targets") or ()),
        before_docs=docs,
        blocked_paths=tuple(blocked),
    )
