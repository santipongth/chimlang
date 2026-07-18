"""MCP server ของชิมลาง (P5-M9, ADR-0005) — ให้ AI agent ภายนอกใช้ชิมลางเป็น tool

รูปแบบ: stdio server แยกตัว (มาตรฐาน MCP local server) **ห่อ REST API เดิมเท่านั้น**
— ไม่มี logic ใหม่ ไม่มีทางลัด: ทุก call วิ่งผ่าน HTTP ไปที่ api/app.py จึงโดน
auth/RBAC/election guard/cap/BudgetGuard ครบทุกด่านเหมือนผู้ใช้ปกติ (GOV-06)

ตั้งค่า (env ของ process MCP — ไม่ใช่ .env ของ repo):
    CHIMLANG_API_URL   default http://localhost:8000
    CHIMLANG_API_KEY   API key ตามระบบ X-API-Key (บังคับเมื่อ AUTH_ENABLED=true)

รัน:  uv run python -m api.mcp_server
ตัวอย่าง config (Claude Code):  claude mcp add chimlang -- uv run python -m api.mcp_server
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "chimlang",
    instructions=(
        "ชิมลาง (CHIMLANG) — Thai social simulation platform. ทุกตัวเลขเป็น simulation "
        "estimate ไม่ใช่โพลจริง; ผลลัพธ์มาพร้อมช่วงความไม่แน่นอนและ fragility index เสมอ. "
        "election scenario ถูกจำกัดโดย governance ที่ API (GOV-02)."
    ),
)


def _request(method: str, path: str, **kwargs) -> dict:
    """เรียก REST API ของชิมลาง — อ่าน env ตอนเรียก (ไม่ cache) เพื่อ test/สลับ key ได้"""
    base = os.environ.get("CHIMLANG_API_URL", "http://localhost:8000").rstrip("/")
    headers = {}
    api_key = os.environ.get("CHIMLANG_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key
    with httpx.Client(base_url=base, headers=headers, timeout=300.0) as client:
        response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"chimlang API {response.status_code}: {detail}")
    return response.json()


@mcp.tool()
def run_dashboard(subject: str, agents: int = 100) -> dict:
    """รัน what-if simulation แล้วคืน Executive Dashboard (brief + fragility + tipping points
    + ผลรายกลุ่ม) — ตัวเลขทุกตัวเป็นช่วง ไม่ใช่ point estimate; agents ถูก cap ที่ 1,000"""
    return _request("GET", "/dashboard.json", params={"subject": subject, "agents": agents})


@mcp.tool()
def compare_red_team(subject: str, agents: int = 100) -> dict:
    """รันคู่ baseline vs +Red Team (seed เดียวกัน) — วัดว่าข้อสรุปทนต่อผู้เล่นปฏิปักษ์
    เสียงดังแค่ไหน (delta_of_delta > 0 = คำชี้แจงได้ผลน้อยลงเมื่อมี red team)"""
    return _request("GET", "/compare.json", params={"subject": subject, "agents": agents})


@mcp.tool()
def resolve_prediction(prediction_id: int, outcome: str, note: str) -> dict:
    """บันทึกผลจริงของ prediction (outcome: true/partial/false, partial = 0.5 ใน Brier)
    — append-only: บันทึกแล้วแก้ไม่ได้ (TRUST-01) ต้องใส่ note อ้างอิงแหล่งผลจริงเสมอ"""
    return _request(
        "POST", f"/predictions/{prediction_id}/resolve", json={"outcome": outcome, "note": note}
    )


@mcp.tool()
def list_runs() -> dict:
    """รันล่าสุดจาก audit log + prediction ที่ครบกำหนดรอ resolve"""
    return _request("GET", "/runs.json")


@mcp.tool()
def list_gallery() -> dict:
    """ผลรันที่เผยแพร่สาธารณะ + คะแนนโหวต agree/disagree (wisdom of crowd vs swarm)"""
    return _request("GET", "/gallery.json")


@mcp.tool()
def get_insights() -> dict:
    """สถิติข้ามทุก run (runs/วัน, exports, predictions รายโดเมน) จาก audit log + registry"""
    return _request("GET", "/insights.json")


def main() -> None:  # pragma: no cover — ทดสอบผ่าน tool functions โดยตรง
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
