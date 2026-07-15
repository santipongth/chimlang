"""PII detector (GOV-01) — ด่านบังคับของทุก ingestion pipeline

หลักการ: fail-closed — สงสัยไว้ก่อน block ทั้งไฟล์แล้วให้มนุษย์ตรวจ
false positive ยอมรับได้ / false negative คือการละเมิด PDPA

ตรวจจับ: ชื่อบุคคล (นำหน้าด้วยคำนำหน้านาม), เบอร์โทรไทย, เลขบัตรประชาชน 13 หลัก
(ตรวจ checksum จริง), อีเมล — allow-list เฉพาะบุคคลสาธารณะในบริบทข่าว
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_ALLOWLIST_PATH = Path(__file__).resolve().parents[1] / "config" / "pii_allowlist.yaml"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# เบอร์ไทย: มือถือ 10 หลัก (06/08/09) และบ้าน 9 หลัก — รองรับคั่นด้วย - หรือเว้นวรรค
_PHONE_RE = re.compile(
    r"(?<![\d-])(?:0[689]\d(?:[- ]?\d{3}){2}\d|0\d[- ]?\d{3}[- ]?\d{4})(?![\d-])"
)
# เลขบัตร 13 หลัก: ติดกันหรือรูปแบบ 1-2345-67890-12-3 (ยืนยันด้วย checksum อีกชั้น)
_THAI_ID_RE = re.compile(r"(?<!\d)(\d(?:[- ]?\d){12})(?!\d)")
# ชื่อบุคคล: คำนำหน้านาม + ชื่อ + นามสกุล (ไทย) — กันคำพ้อง "นายก..." (ตำแหน่ง ไม่ใช่คำนำหน้า)
_NAME_RE = re.compile(
    r"(?:นาย(?!ก(?:รัฐมนตรี|สมาคม|เทศมนตรี|อบจ|อบต))|นางสาว|นาง(?!ฟ้า)|น\.ส\.|ดร\.|ด\.ช\.|ด\.ญ\.)"
    r"\s?([ก-ฮเ-ไ][ก-๙]+)\s+([ก-ฮเ-ไ][ก-๙]+)"
)


def thai_id_checksum_ok(digits: str) -> bool:
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(int(digits[i]) * (13 - i) for i in range(12))
    return (11 - total % 11) % 10 == int(digits[12])


@dataclass(frozen=True)
class PIIFinding:
    kind: str  # person_name | phone | thai_id | email
    value: str
    allowlisted: bool = False


@dataclass(frozen=True)
class PIIReport:
    findings: tuple[PIIFinding, ...]

    @property
    def blocked(self) -> bool:
        return any(not f.allowlisted for f in self.findings)

    @property
    def block_reasons(self) -> list[str]:
        return [f"{f.kind}: {f.value}" for f in self.findings if not f.allowlisted]


@dataclass(frozen=True)
class PIIRedaction:
    text: str
    counts: dict[str, int]

    @property
    def changed(self) -> bool:
        return bool(self.counts)


class PIIRedactionError(RuntimeError):
    """Redacted output still contains non-allowlisted PII."""


def load_allowlist(path: Path | str = DEFAULT_ALLOWLIST_PATH) -> set[str]:
    if not Path(path).exists():
        return set()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {_normalize_name(n) for n in (raw.get("public_figures") or [])}


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


class PIIDetector:
    """ตัวตรวจ PII — ใช้ผ่าน scan()/check(); pipeline ห้ามข้ามด่านนี้ (กฎเหล็กข้อ 1)"""

    def __init__(self, allowlist: set[str] | None = None):
        self._allowlist = {_normalize_name(n) for n in (allowlist or set())}

    def scan(self, text: str) -> list[PIIFinding]:
        findings: list[PIIFinding] = []
        for m in _NAME_RE.finditer(text):
            full_name = _normalize_name(f"{m.group(1)} {m.group(2)}")
            findings.append(
                PIIFinding(
                    kind="person_name",
                    value=full_name,
                    allowlisted=full_name in self._allowlist,
                )
            )
        for m in _PHONE_RE.finditer(text):
            findings.append(PIIFinding(kind="phone", value=m.group(0)))
        for m in _THAI_ID_RE.finditer(text):
            digits = re.sub(r"[- ]", "", m.group(1))
            if thai_id_checksum_ok(digits):  # เลขสุ่มที่ checksum ไม่ผ่าน = ไม่ใช่เลขบัตร
                findings.append(PIIFinding(kind="thai_id", value=m.group(1)))
        for m in _EMAIL_RE.finditer(text):
            findings.append(PIIFinding(kind="email", value=m.group(0)))
        return findings

    def check(self, text: str) -> PIIReport:
        return PIIReport(findings=tuple(self.scan(text)))

    def redact(self, text: str) -> PIIRedaction:
        """Replace detected PII without retaining raw values in the result metadata."""
        counts: dict[str, int] = {}
        person_ids: dict[str, int] = {}

        def bump(kind: str) -> None:
            counts[kind] = counts.get(kind, 0) + 1

        def redact_thai_id(match: re.Match) -> str:
            digits = re.sub(r"[- ]", "", match.group(1))
            if not thai_id_checksum_ok(digits):
                return match.group(0)
            bump("thai_id")
            return "[THAI_ID_REDACTED]"

        def redact_email(match: re.Match) -> str:
            bump("email")
            return "[EMAIL_REDACTED]"

        def redact_phone(match: re.Match) -> str:
            bump("phone")
            return "[PHONE_REDACTED]"

        def redact_person(match: re.Match) -> str:
            full_name = _normalize_name(f"{match.group(1)} {match.group(2)}")
            if full_name in self._allowlist:
                return match.group(0)
            person_id = person_ids.setdefault(full_name, len(person_ids) + 1)
            bump("person_name")
            return f"[PERSON_{person_id}]"

        redacted = _THAI_ID_RE.sub(redact_thai_id, text)
        redacted = _EMAIL_RE.sub(redact_email, redacted)
        redacted = _PHONE_RE.sub(redact_phone, redacted)
        redacted = _NAME_RE.sub(redact_person, redacted)
        return PIIRedaction(text=redacted, counts=counts)

    def redact_and_verify(self, text: str) -> PIIRedaction:
        result = self.redact(text)
        remaining = self.check(result.text)
        if remaining.blocked:
            kinds = sorted({f.kind for f in remaining.findings if not f.allowlisted})
            raise PIIRedactionError("PII redaction verification failed: " + ", ".join(kinds))
        return result
