"""tests P4-M2: PDF ผ่านจุด export เดียว — watermark visible+metadata, ฟอนต์ไทย, fail-closed"""

import pytest
from pypdf import PdfReader

from governance.watermark import WATERMARK_LABEL, WatermarkDisabledError, export_report

MD = """# รายงานทดสอบภาษาไทย

## หัวข้อย่อย

- ประเด็นที่หนึ่ง: เกรงใจและ say-do gap
- ตัวเลขเป็นช่วงเสมอ [10%, 25%]

| กลุ่ม | ค่า |
|---|---|
| คนเมืองรุ่นใหม่ | 42% |

> simulation_estimate — ไม่ใช่โพลจริง
"""


def test_pdf_export_creates_valid_pdf_with_watermark(tmp_path):
    out = export_report(MD, tmp_path / "r.pdf", run_id="pdf-test-01")
    raw = out.read_bytes()
    assert raw.startswith(b"%PDF")

    reader = PdfReader(str(out))
    assert len(reader.pages) >= 1
    # machine-readable watermark ใน metadata (GOV-03)
    subject = reader.metadata.get("/Subject", "")
    assert "chimlang-watermark" in subject
    assert "pdf-test-01" in subject and WATERMARK_LABEL in subject


def test_pdf_export_fail_closed_when_disabled(tmp_path):
    with pytest.raises(WatermarkDisabledError):
        export_report(MD, tmp_path / "blocked.pdf", run_id="x", enabled=False)
    assert not (tmp_path / "blocked.pdf").exists()  # ห้ามมีไฟล์หลุดออกมา


def test_md_export_still_works(tmp_path):
    out = export_report(MD, tmp_path / "r.md", run_id="md-test")
    text = out.read_text(encoding="utf-8")
    assert "chimlang-watermark" in text and "md-test" in text


def test_dashboard_pdf_endpoint():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)
    r = client.get("/dashboard.pdf", params={"agents": 20})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    # PRD pipeline ขั้น 7: Tipping Points ต้องอยู่ใน PDF เสมอแม้ไม่พบจุดพลิก (P5 เก็บตก)
    from io import BytesIO

    pdf_text = "".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    assert "Tipping Points" in pdf_text

    # GOV-02: election + individual = 403; election + aggregate = ได้แต่ต้องติดป้ายบังคับ
    blocked = client.get(
        "/dashboard.pdf", params={"subject": "ผลเลือกตั้งผู้ว่าฯ", "granularity": "individual"}
    )
    assert blocked.status_code == 403

    labeled = client.get("/dashboard.pdf", params={"subject": "ผลเลือกตั้งผู้ว่าฯ", "agents": 20})
    assert labeled.status_code == 200
    from io import BytesIO

    text = "".join(p.extract_text() for p in PdfReader(BytesIO(labeled.content)).pages)
    assert "not_field_poll" in text and "aggregate_only" in text  # ป้าย GOV-02 อยู่ใน PDF จริง
