"""tests M2: extraction parsing, governance gate ของ ingest, integration กับ Neo4j จริง"""

import pytest

from core.config import Settings
from graphlayer.extraction import Extraction, ExtractionError, parse_extraction
from graphlayer.ingest import GovernanceError, ingest_corpus

VALID_JSON = """{
  "entities": [
    {"name": "ค่าธรรมเนียมรถติด", "type": "นโยบาย/มาตรการ"},
    {"name": "กลุ่มไรเดอร์", "type": "กลุ่มผู้มีส่วนได้เสีย"},
    {"name": "กทม.", "type": "องค์กร"}
  ],
  "relations": [
    {"source": "กลุ่มไรเดอร์", "relation": "เรียกร้องข้อยกเว้นจาก", "target": "ค่าธรรมเนียมรถติด",
     "evidence": "ยื่นหนังสือขอความชัดเจน"},
    {"source": "entity ที่ไม่มีในลิสต์", "relation": "x", "target": "กทม.", "evidence": "-"}
  ]
}"""


def test_parse_extraction_valid_and_filters_unknown_entities():
    ex = parse_extraction(VALID_JSON)
    assert len(ex.entities) == 3
    # relation ที่อ้าง entity นอกลิสต์ต้องถูกตัดทิ้ง (กัน graph มี node กำพร้า)
    assert len(ex.relations) == 1
    assert ex.relations[0].relation == "เรียกร้องข้อยกเว้นจาก"


def test_parse_extraction_fenced_json():
    ex = parse_extraction(f"```json\n{VALID_JSON}\n```")
    assert len(ex.entities) == 3


def test_parse_extraction_garbage_raises():
    with pytest.raises(ExtractionError):
        parse_extraction("ขอโทษครับ ผมสกัดไม่ได้")


def test_ingest_refuses_when_pii_detector_disabled(tmp_path):
    # กฎเหล็กข้อ 1: pipeline ต้องปฏิเสธที่จะรันถ้า detector ถูกปิด — ไม่ใช่แค่ข้าม
    settings = Settings(pii_detector_enabled=False, _env_file=None)
    with pytest.raises(GovernanceError):
        ingest_corpus(tmp_path, settings, None, None, dry_run=True)


def test_ingest_dry_run_blocks_pii_file(tmp_path):
    (tmp_path / "2026-01-01-สะอาด.md").write_text("ข่าวนโยบายทั่วไป ไม่มีข้อมูลส่วนบุคคล", encoding="utf-8")
    (tmp_path / "2026-01-02-มีพีไอไอ.md").write_text(
        "ผู้เสียหายคือ นายสมหมาย ทองดี โทร 081-234-5678", encoding="utf-8"
    )
    settings = Settings(_env_file=None)
    results = ingest_corpus(tmp_path, settings, None, None, dry_run=True)
    by_status = {r.doc: r.status for r in results}
    assert by_status["2026-01-01-สะอาด.md"] == "ingested"
    assert by_status["2026-01-02-มีพีไอไอ.md"] == "blocked_pii"


# --- integration กับ Neo4j จริงใน docker (skip อัตโนมัติถ้า stack ไม่รัน) ---


@pytest.fixture
def neo4j_store():
    from graphlayer.store import Neo4jStore

    store = Neo4jStore("bolt://localhost:7687", "neo4j", "chimlang_dev")
    try:
        store.verify()
    except Exception:
        pytest.skip("Neo4j ไม่พร้อม (รัน `docker compose up -d` ก่อน)")
    store.setup()
    yield store
    store.delete_by_source_prefix("__test__")
    store.close()


def test_neo4j_upsert_and_indirect_query(neo4j_store):
    from graphlayer.extraction import Entity, Relation

    # กราฟ 3 ชั้น: นโยบายภาษี → กระทบผู้ประกอบการ → จ้างงานกลุ่มอาชีพ (ทดสอบ 2-hop)
    ex = Extraction(
        entities=(
            Entity("__test__นโยบายภาษีใหม่", "นโยบาย/มาตรการ"),
            Entity("__test__ผู้ประกอบการขนส่ง", "กลุ่มผู้มีส่วนได้เสีย"),
            Entity("__test__กลุ่มพนักงานคลังสินค้า", "กลุ่มผู้มีส่วนได้เสีย"),
        ),
        relations=(
            Relation("__test__นโยบายภาษีใหม่", "เพิ่มต้นทุนของ", "__test__ผู้ประกอบการขนส่ง", "ev1"),
            Relation("__test__ผู้ประกอบการขนส่ง", "จ้างงาน", "__test__กลุ่มพนักงานคลังสินค้า", "ev2"),
        ),
    )
    neo4j_store.upsert_extraction(ex, source_doc="__test__/doc1.md", doc_date="2026-01-01")
    # upsert ซ้ำต้อง idempotent (MERGE)
    neo4j_store.upsert_extraction(ex, source_doc="__test__/doc1.md", doc_date="2026-01-01")

    path = neo4j_store.query_indirect(
        "__test__นโยบายภาษีใหม่", "__test__กลุ่มพนักงานคลังสินค้า", max_hops=3
    )
    assert path is not None
    assert path.nodes[0] == "__test__นโยบายภาษีใหม่"
    assert path.nodes[-1] == "__test__กลุ่มพนักงานคลังสินค้า"
    assert len(path.relations) == 2  # ความสัมพันธ์ทางอ้อม 2 hop

    neighbors = neo4j_store.neighbors("__test__ผู้ประกอบการขนส่ง")
    assert len(neighbors) == 2
