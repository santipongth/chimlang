"""tests PII detector (GOV-01) — test cases ภาษาไทยตาม M2 checklist"""

from governance.pii import PIIDetector, load_allowlist, thai_id_checksum_ok


def _valid_thai_id() -> str:
    """สร้างเลขบัตรที่ checksum ถูกต้อง (เลขทดสอบ ไม่ใช่ของบุคคลจริง)"""
    base = "120050008888"  # 12 หลักสมมติ
    total = sum(int(base[i]) * (13 - i) for i in range(12))
    return base + str((11 - total % 11) % 10)


def test_thai_person_name_blocked():
    report = PIIDetector().check("ผู้ร้องเรียนคือ นายสมชาย ใจดี อายุ 45 ปี")
    assert report.blocked
    assert any(f.kind == "person_name" and f.value == "สมชาย ใจดี" for f in report.findings)


def test_public_figure_allowlisted_not_blocked():
    detector = PIIDetector(allowlist={"ชัชชาติ สิทธิพันธุ์"})
    report = detector.check("นายชัชชาติ สิทธิพันธุ์ แถลงนโยบายวันนี้")
    assert not report.blocked  # บุคคลสาธารณะในบริบทข่าว = ผ่าน
    assert report.findings[0].allowlisted


def test_position_words_not_false_positive():
    # "นายก..." คือตำแหน่ง ไม่ใช่คำนำหน้าชื่อ — corpus จริงมีคำนี้เยอะ
    report = PIIDetector().check("นายกสมาคมผู้ประกอบการ กล่าวว่ามาตรการนี้กระทบหนัก")
    assert not report.blocked


def test_thai_phone_formats_blocked():
    detector = PIIDetector()
    assert detector.check("ติดต่อ 0812345678 ได้เลย").blocked
    assert detector.check("โทร 081-234-5678 นะครับ").blocked
    assert detector.check("เบอร์บ้าน 02-123-4567").blocked
    # ตัวเลขทั่วไปที่ไม่ใช่เบอร์ ต้องไม่ถูก flag
    assert not detector.check("งบประมาณ 6 หมื่นล้านบาทต่อปี ปี 2565").blocked


def test_thai_id_checksum_validation():
    detector = PIIDetector()
    valid = _valid_thai_id()
    assert thai_id_checksum_ok(valid)
    assert detector.check(f"เลขบัตร {valid} ของผู้สมัคร").blocked
    # เลข 13 หลักที่ checksum ผิด = ตัวเลขธรรมดา ไม่ flag
    invalid = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert not detector.check(f"รหัสอ้างอิง {invalid} ในระบบ").blocked


def test_email_blocked():
    assert PIIDetector().check("ส่งเรื่องมาที่ somchai.j@example.co.th").blocked


def test_clean_corpus_files_pass():
    # corpus ที่ร่างไว้ทั้ง 12 ไฟล์ต้องผ่าน detector (ออกแบบมาไม่มี PII)
    from pathlib import Path

    detector = PIIDetector(allowlist=load_allowlist())
    corpus = Path(__file__).resolve().parents[1] / "data" / "samples" / "corpus"
    for doc in sorted(corpus.glob("2026-*.md")):
        report = detector.check(doc.read_text(encoding="utf-8"))
        assert not report.blocked, f"{doc.name}: {report.block_reasons}"


def test_allowlist_file_loads():
    names = load_allowlist()
    assert "ชัชชาติ สิทธิพันธุ์" in names


def test_redact_and_verify_replaces_all_supported_pii_types():
    thai_id = _valid_thai_id()
    text = (
        "นายสมชาย ใจดี ติดต่อ somchai@example.com โทร 081-234-5678 "
        f"เลขบัตร {thai_id} และนายสมชาย ใจดี จะตอบกลับ"
    )
    result = PIIDetector().redact_and_verify(text)

    assert result.counts == {"thai_id": 1, "email": 1, "phone": 1, "person_name": 2}
    assert result.text.count("[PERSON_1]") == 2
    assert "[PHONE_REDACTED]" in result.text
    assert "[EMAIL_REDACTED]" in result.text
    assert "[THAI_ID_REDACTED]" in result.text
    assert "สมชาย ใจดี" not in result.text
    assert "081-234-5678" not in result.text
    assert not PIIDetector().check(result.text).blocked


def test_redaction_preserves_allowlisted_public_figure():
    detector = PIIDetector(allowlist={"ชัชชาติ สิทธิพันธุ์"})
    result = detector.redact_and_verify("นายชัชชาติ สิทธิพันธุ์ แถลงข่าว")

    assert result.text == "นายชัชชาติ สิทธิพันธุ์ แถลงข่าว"
    assert result.counts == {}
