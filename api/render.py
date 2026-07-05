"""Render Dashboard เป็น HTML (DASH-01..04) — self-contained, ไทย, ผ่าน watermark ที่ layer export"""

from html import escape

from api.dashboard import Dashboard

_CSS = """
body{font-family:system-ui,'Segoe UI',sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;
color:#1a1a1a;line-height:1.6}
.brief{background:#f4f7fb;border-left:4px solid #2563eb;padding:1rem 1.25rem;border-radius:6px}
.brief .risk{color:#b91c1c}.brief .opportunity{color:#047857}
table{border-collapse:collapse;width:100%;margin:1rem 0}
th,td{border:1px solid #ddd;padding:.5rem .7rem;text-align:left}th{background:#f4f4f5}
.band-สูง{background:#fee2e2}.band-กลาง{background:#fef9c3}.band-ต่ำ{background:#dcfce7}
.wm{color:#92400e;background:#fffbeb;border:1px solid #fde68a;padding:.6rem 1rem;border-radius:6px;
font-size:.9rem}
.voice{border-left:3px solid #cbd5e1;padding:.4rem .8rem;margin:.5rem 0}
.voice .think{color:#64748b;font-style:italic}
"""


def render_dashboard_html(dash: Dashboard) -> str:
    b = dash.brief
    lo, hi = b.headline_range
    brief_items = "".join(f'<li class="{escape(ln.kind)}">{escape(ln.text)}</li>' for ln in b.lines)
    heat_rows = "".join(
        f"<tr><td>{escape(c.segment_or_role if hasattr(c, 'segment_or_role') else c['name'])}</td>"
        f'<td class="band-{escape(c.band if hasattr(c, "band") else c["band"])}">'
        f"{c.risk if hasattr(c, 'risk') else c['risk']} "
        f"({escape(c.band if hasattr(c, 'band') else c['band'])})</td></tr>"
        for c in dash.heatmap
    )
    segs = sorted({s for sc in dash.scenarios for s in sc.belief_by_segment})
    head = "".join(f"<th>{escape(sc.name)}</th>" for sc in dash.scenarios)
    scen_rows = "".join(
        f"<tr><td>{escape(seg)}</td>"
        + "".join(f"<td>{sc.belief_by_segment.get(seg, 0):.0%}</td>" for sc in dash.scenarios)
        + "</tr>"
        for seg in segs
    )
    voices = "".join(
        f'<div class="voice"><div class="think">🧠 {escape(v.get("private", ""))}</div>'
        f"<div>📢 {escape(v.get('public', '') or '(เลือกไม่โพสต์)')}</div>"
        f"<small>{escape(v.get('segment', ''))}</small></div>"
        for v in dash.voices
    )
    return f"""<!doctype html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Executive Dashboard — {escape(dash.subject)}</title><style>{_CSS}</style></head><body>
<div class="wm">⚠️ AI simulation — not a real poll | ผลจำลอง ไม่ใช่โพลจริง</div>
<h1>Executive Dashboard: {escape(dash.subject)}</h1>
<h2>Executive Brief (DASH-01)</h2>
<div class="brief"><ul>{brief_items}</ul>
<p><b>ช่วงผลหลัก:</b> [{lo:+.0%}, {hi:+.0%}] &nbsp;|&nbsp; <b>Fragility:</b> {b.fragility_index}/100
— {escape(b.confidence_label)}</p></div>
<h2>Risk Heatmap (DASH-02)</h2>
<table><tr><th>บทบาท/กลุ่ม</th><th>risk (likelihood×damage)</th></tr>{heat_rows}</table>
<h2>Scenario Comparison (DASH-03) — สัดส่วนผู้เชื่อรายกลุ่ม</h2>
<table><tr><th>กลุ่ม</th>{head}</tr>{scen_rows}</table>
<h2>Synthetic Voices (DASH-04)</h2>{voices or "<p>(ไม่มีตัวอย่างเสียงในรอบนี้)</p>"}
</body></html>"""
