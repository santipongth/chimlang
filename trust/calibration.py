"""Calibration dashboard + Public benchmark page (TRUST-02 / หลัก Honesty over impressiveness)

benchmark page เผยแพร่ทั้ง "ผ่านและไม่ผ่าน" เสมอ — ห้ามคัดเฉพาะผลดี (AC ของ TRUST-03)
ทุกหน้าออกผ่าน watermark เท่านั้น (ไปเรียก governance.watermark.export_report ที่ script)
"""

import json
from datetime import date
from pathlib import Path

from governance.store import DomainCalibration


def render_calibration_dashboard(summary: list[DomainCalibration], *, as_of: date) -> str:
    lines = [
        "## Calibration Dashboard (TRUST-02)",
        "",
        f"- ณ วันที่: {as_of.isoformat()} | Brier score: 0 = สมบูรณ์แบบ, 0.25 = เดามั่ว (baseline)",
        "",
    ]
    if not summary:
        lines.append(
            "_ยังไม่มี prediction ที่ resolve แล้ว — dashboard จะเติมเมื่อคำทำนายครบกำหนดและถูกวัดผล_"
        )
        return "\n".join(lines)
    lines += [
        "| โดเมน | resolved | mean Brier | baseline | ดีกว่า baseline? |",
        "|---|---|---|---|---|",
    ]
    for row in summary:
        lines.append(
            f"| {row.domain} | {row.resolved} | {row.mean_brier:.3f} | {row.baseline_brier:.2f} "
            f"| {'✅' if row.better_than_baseline else '❌'} |"
        )
    return "\n".join(lines)


def render_benchmark_page(
    *,
    hindcast_json_path: Path | str,
    calibration: list[DomainCalibration],
    as_of: date,
) -> str:
    """Public benchmark page — hindcast (ผ่าน/ไม่ผ่านครบทุกเหตุการณ์) + calibration + ข้อจำกัด"""
    hc = json.loads(Path(hindcast_json_path).read_text(encoding="utf-8"))
    lines = [
        "# ชิมลาง — Public Benchmark (ผลทั้งหมด ทั้งผ่านและไม่ผ่าน)",
        "",
        "> ⚠️ ทุกตัวเลขในหน้านี้เป็น simulation_estimate ระดับ aggregate — not_field_poll (GOV-02)",
        "",
        "## Hindcast benchmark (TRUST-03)",
        "",
        f"- รันเมื่อ: {hc['ran_at']} | agents/target: {hc['agents_per_target']} "
        f"(ภายใต้ cap พัฒนา ≤ {hc['max_agents_dev']}) | ต้นทุน: ${hc['spent_usd']:.4f}",
        f"- ผล: **ผ่าน {hc['passed']}/{hc['total_events']} เหตุการณ์** "
        f"(เกณฑ์เฟส: ≥ {hc['pass_required']})",
        "",
        "| เหตุการณ์ | target | ทำนาย | ผลจริง | ถูก? |",
        "|---|---|---|---|---|",
    ]
    for ev in hc["events"]:
        for t in ev["targets"]:
            lines.append(
                f"| {ev['event_id']} | {t['id']} | {t['predicted']} | {t['truth']} "
                f"| {'✅' if t['correct'] else '❌'} |"
            )
    lines += [
        "",
        render_calibration_dashboard(calibration, as_of=as_of),
        "",
        "## ข้อจำกัดที่ต้องรู้ (เผยแพร่คู่ผลลัพธ์เสมอ)",
        "",
        "1. เหตุการณ์ hindcast อยู่ใน training data ของ LLM — leak test คุมการเผยผลชัดแจ้ง "
        "(รายละเอียดใน docs/reports/) แต่ prior contamination ตัดไม่ได้ 100% "
        "→ ผล hindcast เป็นเงื่อนไขจำเป็น ไม่ใช่ข้อพิสูจน์สุดท้าย",
        "2. รันภายใต้ข้อจำกัดช่วงพัฒนา (≤ 10 agents) — ผลที่ scale จริงต้องวัดซ้ำ",
        "3. Calibration ที่แท้จริงมาจากคำทำนายเหตุการณ์อนาคตที่ resolve ตามกำหนดเท่านั้น",
        "4. ผลต่างกันได้เล็กน้อยระหว่างรอบรัน (LLM non-determinism แม้ pin seed) — "
        "target ที่เสียงโหวตก้ำกึ่งอาจพลิกข้ามรอบ (สังเกตจริง: 4/5 → 5/5 ในสองรอบติดกัน); "
        "รายงานทุกรอบถูกเก็บถาวร ไม่เลือกเฉพาะรอบที่สวยที่สุด",
    ]
    return "\n".join(lines)
