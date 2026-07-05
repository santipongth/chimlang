"""Ingestion pipeline (SIM-01 ขั้น 1–3): corpus → PII gate → extraction → Neo4j

กฎเหล็กข้อ 1: ทุกไฟล์ต้องผ่าน PII detector ก่อน — พบ PII ที่ไม่อยู่ใน allow-list
= block ทั้งไฟล์ + บันทึกเหตุผล และ pipeline ปฏิเสธที่จะรันถ้า detector ถูกปิด
"""

from dataclasses import dataclass
from pathlib import Path

from core.config import Settings
from core.llm import LLMAdapter
from governance.pii import PIIDetector, load_allowlist
from graphlayer.extraction import ExtractionError, extract
from graphlayer.normalize import normalize_extraction
from graphlayer.store import Neo4jStore
from trust.hindcast.filters import extract_doc_date


class GovernanceError(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestResult:
    doc: str
    status: str  # ingested | blocked_pii | failed_extraction
    detail: str
    entities: int = 0
    relations: int = 0


def ingest_corpus(
    corpus_dir: Path | str,
    settings: Settings,
    adapter: LLMAdapter | None,
    store: Neo4jStore | None,
    *,
    dry_run: bool = False,
    on_progress=None,
) -> list[IngestResult]:
    """dry_run=True: ตรวจ PII อย่างเดียว ไม่เรียก LLM/ไม่เขียน graph"""
    if not settings.pii_detector_enabled:
        raise GovernanceError(
            "PII_DETECTOR_ENABLED=false — pipeline นำเข้าข้อมูลห้ามรันโดยไม่มี PII detector (GOV-01)"
        )
    detector = PIIDetector(allowlist=load_allowlist())
    results: list[IngestResult] = []

    for doc_path in sorted(Path(corpus_dir).glob("*.md")):
        if doc_path.name.upper().startswith("README"):
            continue
        text = doc_path.read_text(encoding="utf-8")

        report = detector.check(text)
        if report.blocked:
            results.append(
                IngestResult(
                    doc=doc_path.name,
                    status="blocked_pii",
                    detail="; ".join(report.block_reasons),
                )
            )
        elif dry_run:
            results.append(IngestResult(doc=doc_path.name, status="ingested", detail="dry-run"))
        else:
            doc_date = extract_doc_date(doc_path.name)
            try:
                ex = normalize_extraction(extract(adapter, text, seed=settings.default_seed))
            except ExtractionError as e:
                results.append(
                    IngestResult(doc=doc_path.name, status="failed_extraction", detail=str(e))
                )
            else:
                store.upsert_extraction(
                    ex,
                    source_doc=doc_path.name,
                    doc_date=doc_date.isoformat() if doc_date else "unknown",
                )
                results.append(
                    IngestResult(
                        doc=doc_path.name,
                        status="ingested",
                        detail="ok",
                        entities=len(ex.entities),
                        relations=len(ex.relations),
                    )
                )
        if on_progress:
            on_progress(results[-1])
    return results
