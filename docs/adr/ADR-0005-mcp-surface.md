# ADR-0005 — MCP surface: stdio server ห่อ REST เดิม (P5-M9)

- วันที่: 12 ก.ค. 2026 | สถานะ: ใช้งาน (ผู้ใช้สั่ง "ทำต่อ" กับ backlog — ผู้ใช้ veto/ปรับได้)
- บริบท: SwarmSight เปิด MCP tools (create-run/get-run/list-runs) ให้ AI agent ภายนอกใช้ระบบเป็นเครื่องมือ — ของเราต้องตัดสินใจ transport + auth โดยไม่เจาะ governance

## การตัดสินใจ

1. **Transport = stdio server แยกตัว** (`api/mcp_server.py`, official `mcp` SDK) — มาตรฐาน
   local MCP server ที่ Claude Code/Desktop และ client อื่น spawn ได้ตรงๆ; ไม่ mount เข้า
   FastAPI (เลี่ยงความซับซ้อน session manager ของ streamable HTTP จนกว่าจะมี use case remote)
2. **ห่อ REST เท่านั้น — ห้ามมี logic ใหม่/ทางลัด**: ทุก tool call วิ่ง HTTP ไป api/app.py
   → auth/RBAC (GOV-06), election guard (GOV-02), PII (GOV-01), cap/BudgetGuard บังคับครบ
   เหมือนผู้ใช้ปกติ ไม่มี privileged path
3. **Auth = API key เดิมผ่าน env ของ process MCP** (`CHIMLANG_API_KEY` → header X-API-Key)
   — สิทธิ์ของ agent ภายนอก = role ของ key ที่ผู้ดูแลออกให้ (viewer/analyst/operator/admin)
   ไม่มีการสร้างระบบ auth ใหม่
4. **Tools ชุดแรก (7 ตัว, read-mostly)**: run_dashboard, compare_red_team, get_calibration,
   resolve_prediction (เขียนแบบ append-only ตัวเดียว), list_runs, list_gallery, get_insights
   — ไม่เปิด share gallery / watchlist write ผ่าน MCP จนกว่าจะมี use case จริง
5. Dependency ใหม่: `mcp` (official SDK, MIT) — จุดเดียวที่ใช้คือ api/mcp_server.py

## ทางเลือกที่ไม่เอา

- Mount streamable HTTP บน FastAPI — เลื่อน: ซับซ้อนกว่า (session/lifespan) และยังไม่มี client remote จริง; stdio ครอบ use case "ใช้ชิมลางจาก Claude Code บนเครื่องเดียวกัน" ครบ
- Manifest JSON เฉยๆ แบบ SwarmSight (.lovable/mcp) — ไม่เอา: ไม่ใช่มาตรฐาน MCP จริง client ใช้ไม่ได้

## วิธีใช้

```
claude mcp add chimlang --env CHIMLANG_API_KEY=<key> -- uv run python -m api.mcp_server
```
(dev ที่ AUTH_ENABLED=false ไม่ต้องใส่ key — ทุก request เป็น dev-admin ตามเดิม)
