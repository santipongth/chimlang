"""Watermark module (GOV-03) — ทางผ่านเดียวของทุก export ก่อนถึงมือผู้ใช้ (กฎเหล็กข้อ 4)

ทุก export ฝัง 2 ชั้น:
- visible: ป้ายหัว/ท้ายเอกสารที่คนอ่านเห็น "AI simulation — not a real poll"
- machine-readable: JSON ใน HTML comment (run_id, วันที่, ป้าย) ให้ระบบอื่นตรวจอัตโนมัติ

fail-closed: WATERMARK_ENABLED=false = ปฏิเสธ export ทั้งหมด (แบบเดียวกับ PII detector)
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

WATERMARK_LABEL = "AI simulation — not a real poll"
_MACHINE_RE = re.compile(r"<!--\s*chimlang-watermark:(\{.*?\})\s*-->", re.DOTALL)


class WatermarkDisabledError(RuntimeError):
    def __init__(self):
        super().__init__("WATERMARK_ENABLED=false — ระบบปฏิเสธ export ทุกชนิด (GOV-03 / กฎเหล็กข้อ 4)")


@dataclass(frozen=True)
class WatermarkInfo:
    run_id: str
    exported_at: str
    label: str


def apply_watermark(content: str, *, run_id: str, enabled: bool = True) -> str:
    if not enabled:
        raise WatermarkDisabledError()
    info = {
        "run_id": run_id,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "label": WATERMARK_LABEL,
    }
    machine = f"<!-- chimlang-watermark:{json.dumps(info, ensure_ascii=False)} -->"
    visible_top = (
        f"> ⚠️ **{WATERMARK_LABEL}** — ผลจำลองโดย AI (ชิมลาง) ไม่ใช่โพลจริง "
        f"| run: `{run_id}` | export: {info['exported_at']}"
    )
    visible_bottom = f"> ⚠️ {WATERMARK_LABEL} | run `{run_id}`"
    return f"{machine}\n{visible_top}\n\n{content}\n\n---\n{visible_bottom}\n"


def watermark_payload(
    payload: dict,
    *,
    run_id: str,
    manifest_hash: str,
    enabled: bool = True,
) -> dict:
    """Wrap a JSON snapshot with visible and machine-readable provenance."""
    if not enabled:
        raise WatermarkDisabledError()
    return {
        "watermark": {
            "label": WATERMARK_LABEL,
            "note": "ผลจำลองโดย AI (ชิมลาง) ไม่ใช่โพลจริง",
            "run_id": run_id,
            "manifest_hash": manifest_hash,
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        "snapshot": payload,
    }


def verify_watermark(text: str) -> WatermarkInfo | None:
    """อ่าน machine-readable watermark กลับ — None ถ้าไม่พบ (ใช้ตรวจใน test/pipeline)"""
    m = _MACHINE_RE.search(text)
    if not m:
        return None
    data = json.loads(m.group(1))
    return WatermarkInfo(
        run_id=data["run_id"], exported_at=data["exported_at"], label=data["label"]
    )


def export_report(content: str, path: Path | str, *, run_id: str, enabled: bool = True) -> Path:
    """จุด export เดียวของระบบ — writer ทุกตัวต้องผ่านฟังก์ชันนี้ ห้ามเขียนไฟล์รายงานตรงๆ

    นามสกุล .pdf = render เป็น PDF (P4-M2) — watermark ครบสองชั้นเช่นเดียวกับ markdown
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".pdf":
        if not enabled:
            raise WatermarkDisabledError()
        from governance.pdf import render_pdf  # import ที่นี่ — ฝั่ง md ไม่ต้องแบก fpdf

        exported_at = datetime.now(UTC).isoformat(timespec="seconds")
        return render_pdf(content, path, run_id=run_id, exported_at=exported_at)
    path.write_text(apply_watermark(content, run_id=run_id, enabled=enabled), encoding="utf-8")
    return path
