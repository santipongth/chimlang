"""PDF renderer สำหรับ export (GOV-03, P4-M2) — เรียกผ่าน governance.watermark.export_report เท่านั้น

watermark 2 ชั้นใน PDF:
- visible: แถบหัวกระดาษ + ท้ายกระดาษทุกหน้า "AI simulation — not a real poll | run | เวลา"
- machine-readable: JSON เดียวกับฝั่ง markdown ใน PDF metadata (subject) — อ่านกลับด้วย pypdf ได้

ฟอนต์ไทย: Sarabun (OFL — ดู assets/fonts/OFL.txt) ฝังในไฟล์ + text shaping ผ่าน uharfbuzz
เพื่อให้สระ/วรรณยุกต์ไทยวางตำแหน่งถูก
"""

import json
import re
from pathlib import Path

from fpdf import FPDF

from governance.watermark import WATERMARK_LABEL

_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


class _ChimlangPDF(FPDF):
    """หัว/ท้ายกระดาษ watermark ทุกหน้าอัตโนมัติ"""

    def __init__(self, banner: str):
        super().__init__(format="A4")
        self._banner = banner

    def header(self):
        self.set_font("SarabunTH", "", 8)
        self.set_text_color(150, 110, 20)
        self.cell(0, 6, self._banner, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(30, 35, 45)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("SarabunTH", "", 8)
        self.set_text_color(150, 110, 20)
        self.cell(0, 6, f"{self._banner}  |  หน้า {self.page_no()}", align="C")


def _strip_md(line: str) -> str:
    return _MD_BOLD.sub(r"\1", line).replace("`", "")


def render_pdf(content_md: str, path: Path, *, run_id: str, exported_at: str) -> Path:
    """แปลงรายงาน markdown (โครงเรียบ) เป็น PDF ฟอนต์ไทย + watermark ครบสองชั้น"""
    banner = f"⚠ {WATERMARK_LABEL} | run {run_id} | {exported_at}"
    pdf = _ChimlangPDF(banner)
    pdf.add_font("SarabunTH", "", _FONT_DIR / "Sarabun-Regular.ttf")
    pdf.add_font("SarabunTH", "B", _FONT_DIR / "Sarabun-Bold.ttf")
    try:
        pdf.set_text_shaping(True)  # วรรณยุกต์/สระไทยวางถูกตำแหน่ง
    except Exception:
        pass  # uharfbuzz ไม่พร้อม — ยัง render ได้แต่ shaping ลดลง
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # machine-readable watermark ใน metadata (GOV-03)
    info = {"run_id": run_id, "exported_at": exported_at, "label": WATERMARK_LABEL}
    pdf.set_title(f"ชิมลาง — {run_id}")
    pdf.set_subject(f"chimlang-watermark:{json.dumps(info, ensure_ascii=False)}")
    pdf.set_creator("chimlang (governed export)")

    for raw in content_md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(3)
            continue
        text = _strip_md(line.strip())
        if line.startswith("# "):
            pdf.set_font("SarabunTH", "B", 16)
            pdf.multi_cell(0, 8, text[2:], new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("## "):
            pdf.set_font("SarabunTH", "B", 13)
            pdf.multi_cell(0, 7, text[3:], new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("### "):
            pdf.set_font("SarabunTH", "B", 11)
            pdf.multi_cell(0, 6, text[4:], new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("|"):
            pdf.set_font("SarabunTH", "", 9)
            cells = [c.strip() for c in text.strip("|").split("|")]
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue  # แถวเส้นคั่นตาราง markdown
            pdf.multi_cell(0, 5.5, "   ".join(cells), new_x="LMARGIN", new_y="NEXT")
        elif line.startswith(">"):
            pdf.set_font("SarabunTH", "", 9)
            pdf.set_text_color(120, 90, 20)
            pdf.multi_cell(0, 5.5, text.lstrip("> "), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(30, 35, 45)
        else:
            pdf.set_font("SarabunTH", "", 10)
            pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path
