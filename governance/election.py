"""Election Mode (GOV-02) — บังคับ aggregate-only + ป้ายกำกับ + ปิด Sim-to-Signal

เมื่อ scenario ถูกจัดเป็นการเลือกตั้ง/การเมือง (auto-classify จากคำสำคัญ + manual flag):
- output ระดับต่ำกว่า segment ถูก block
- ผลทุกชิ้นติดป้าย simulation_estimate / not_field_poll / aggregate_only
- Sim-to-Signal API ถูกปิด
บังคับที่ระดับโค้ด (fail-safe): manual flag เปิดได้เสมอ, auto-classify เปิดเพิ่มไม่ปิด
"""

import re
from dataclasses import dataclass

# คำสำคัญบ่งชี้ scenario การเมือง/เลือกตั้ง (ไทย) — ครอบคลุมทั้งระดับชาติ/ท้องถิ่น/พรรค
_ELECTION_TERMS = [
    "เลือกตั้ง",
    "ผู้ว่าราชการ",
    "ผู้ว่าฯ",
    "ส.ส.",
    "ส.ว.",
    "ส.ก.",
    "หาเสียง",
    "ผู้สมัคร",
    "พรรคการเมือง",
    "พรรคฝ่ายค้าน",
    "พรรครัฐบาล",
    "นายกรัฐมนตรี",
    "โหวตนายก",
    "ลงคะแนนเสียง",
    "คูหา",
    "กกต.",
    "ประชามติ",
]

ELECTION_LABELS = ("simulation_estimate", "not_field_poll", "aggregate_only")


@dataclass(frozen=True)
class ElectionModeError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ElectionClassification:
    is_election: bool
    matched_terms: tuple[str, ...]
    source: str  # "manual" | "auto" | "manual+auto" | "none"


def classify_scenario(text: str, *, manual_flag: bool = False) -> ElectionClassification:
    matched = tuple(t for t in _ELECTION_TERMS if t in text)
    auto = len(matched) > 0
    if manual_flag and auto:
        source = "manual+auto"
    elif manual_flag:
        source = "manual"
    elif auto:
        source = "auto"
    else:
        source = "none"
    return ElectionClassification(
        is_election=manual_flag or auto, matched_terms=matched, source=source
    )


@dataclass(frozen=True)
class ElectionPolicy:
    """นโยบายที่บังคับใช้เมื่ออยู่ใน election mode — gate ก่อน export/ก่อนเรียก signal"""

    classification: ElectionClassification

    @property
    def active(self) -> bool:
        return self.classification.is_election

    def require_aggregate(self, granularity: str) -> None:
        """granularity ต้องเป็น 'aggregate' หรือ 'segment' — ต่ำกว่านั้น block ใน election mode"""
        if self.active and granularity not in ("aggregate", "segment"):
            raise ElectionModeError(
                f"election mode: ห้าม output ระดับ '{granularity}' — "
                "อนุญาตเฉพาะ aggregate/segment (GOV-02)"
            )

    def guard_sim_to_signal(self) -> None:
        if self.active:
            raise ElectionModeError(
                "election mode: Sim-to-Signal ถูกปิด — ห้ามแปลงผลเลือกตั้งเป็น feature เชิงปริมาณ (GOV-02)"
            )

    def apply_labels(self, text: str) -> str:
        if not self.active:
            return text
        banner = (
            "> 🗳️ **ELECTION MODE** — ป้ายบังคับ: "
            + " / ".join(f"`{lbl}`" for lbl in ELECTION_LABELS)
            + "\n> ผลนี้เป็นการจำลอง ไม่ใช่โพลจริง และไม่ใช่คำทำนายผลเลือกตั้ง\n\n"
        )
        return banner + text

    def has_all_labels(self, text: str) -> bool:
        return all(lbl in text for lbl in ELECTION_LABELS)


# --- GOV-05: กันการผลิตคอนเทนต์ชักจูง (regression guard) ---

# คำขอที่ส่อว่าให้ "ผลิตสารเพื่อเผยแพร่" ไม่ใช่ "วิเคราะห์ปฏิกิริยาต่อสาร"
_PERSUASION_REQUEST = re.compile(
    r"(เขียน|ร่าง|แต่ง|ช่วย(ทำ|คิด))\s*(โฆษณา|ad\s*copy|สคริปต์หาเสียง|สปอต|"
    r"โพสต์หาเสียง|แคปชั่นหาเสียง|คำขวัญหาเสียง|ข้อความชวนเชื่อ)",
    re.IGNORECASE,
)


class PersuasionContentError(Exception):
    pass


def guard_no_persuasion_content(request: str) -> None:
    """เรียกก่อนรับคำสั่งสร้างเนื้อหา — คำขอผลิตสารชักจูงถูกปฏิเสธ (GOV-05 / กฎเหล็กข้อ 5)"""
    if _PERSUASION_REQUEST.search(request):
        raise PersuasionContentError(
            "ระบบไม่ผลิตคอนเทนต์ชักจูง/หาเสียงจากผลจำลอง — ได้เพียง insight ว่ากลุ่มใดกังวลเรื่องใด (GOV-05)"
        )
