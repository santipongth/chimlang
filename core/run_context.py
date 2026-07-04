"""RunContext — สถานะกลางของ 1 simulation run (reproducibility + governance flags)

กฎเหล็กข้อ 2: ทุก code path ที่ดึงข้อมูลภายนอก (SIM-11 ในอนาคต) ต้องเรียก
`ensure_external_retrieval_allowed(ctx)` ก่อนเสมอ — hindcast_mode เปิด = block ตาย
"""

from dataclasses import dataclass
from datetime import date


class ExternalRetrievalBlockedError(RuntimeError):
    def __init__(self):
        super().__init__(
            "external retrieval ถูก block: run นี้อยู่ใน hindcast_mode (TRUST-03 / กฎเหล็กข้อ 2)"
        )


@dataclass(frozen=True)
class RunContext:
    run_id: str
    seed: int
    hindcast_mode: bool = False
    cutoff_date: date | None = None

    def __post_init__(self):
        if self.hindcast_mode and self.cutoff_date is None:
            raise ValueError("hindcast_mode ต้องระบุ cutoff_date เสมอ")


def ensure_external_retrieval_allowed(ctx: RunContext) -> None:
    """gate บังคับก่อน external retrieval ทุกครั้ง — fail-closed ใน hindcast mode"""
    if ctx.hindcast_mode:
        raise ExternalRetrievalBlockedError()
