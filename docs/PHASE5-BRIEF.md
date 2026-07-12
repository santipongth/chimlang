# PHASE 5 BRIEF — SwarmSight Integration (UI ยึด studio + ปิด gap)

เริ่ม 12 ก.ค. 2026 — **ผู้ใช้ approve**: "วางแผนที่ดีที่สุดให้ฉัน แล้วเริ่มได้เลย"
ที่มา: `docs/reports/swarmsight-research-v2.md` (gap analysis 13 ข้อ + UI spec แกะจากโค้ด studio จริง)
หลักการ: ทุก milestone เป็น **vertical slice** (จบแล้วใช้ได้จริง end-to-end ไม่มี UI หลอกที่ backend ยังไม่มี)

## กติกาที่สืบทอด (ห้ามหย่อน)

- governance ทุกด่านคงเดิม: watermark / audit / registry append-only / election GOV-02 / PII GOV-01 / GOV-05
- seed determinism + BudgetGuard ทุก run | test เขียวก่อน commit | ไทย first-class
- **ไม่เลียนจุดอ่อน SwarmSight**: ไม่มี Math.random ไร้ seed, ไม่มี outcome mutable, ไม่มี silent agent-fail, ไม่มี ingest ที่ไม่ผ่าน PII gate
- Design convention ใหม่ (จาก studio): **metric ทุกตัวใน UI ต้องมี tooltip อธิบายสูตร inline**

## Milestones

### P5-M1 — UI shell ตาม studio (frontend ล้วน) ✅ (12 ก.ค. 2026)
- [x] tokens เพิ่มใน `web/src/index.css`: `sidebar-accent`, `ring`, `chart-1..5` (hue 160/240/80/30/300), popover
- [x] Sidebar nav แบบ studio: icon 16px + `rounded-lg px-3 py-2`, active = `bg-sidebar-accent`, โลโก้ icon ใน `bg-primary/10` + ชื่อ serif, รองรับ badge ตัวเลข (ใช้จริง M5)
- [x] Page header pattern ทุกหน้า: eyebrow (uppercase tracking-wider + icon primary) → serif text-4xl → คำอธิบาย
- [x] Wizard: template gallery แบบ card 2 คอลัมน์ (แทน/เสริม chips เดิม), selection card `border-primary bg-primary/5`
- [x] Dashboard: โครง tabs (ผลรวม/เสียง/รายงาน) เตรียมรับ canvas ใน M2
- [x] `npm run build` ผ่าน + tests เดิมเขียว

### P5-M2 — Tipping point detection + opinion swarm canvas ✅ (12 ก.ค. 2026)
- [x] `simulation/tipping.py`: detect รอบที่ |Δ belief share| ≥ 0.15/round จาก reasoning trail (เทียบเท่า 0.25 บนสเกล stance ของ SwarmSight — ดู docstring เหตุผล) → `[{round, before, after, delta}]`
- [x] บังคับใน output: dashboard.json (key `tipping_points` มีเสมอ) + รายงาน what-if (section แสดงเสมอแม้ไม่พบ — PRD pipeline ขั้น 7)
- [x] Opinion canvas ระดับ segment: x=เชื่อ baseline, y=เชื่อหลังคำชี้แจง, ขนาดฟอง=สัดส่วนประชากร, เส้นทแยง=ไม่เปลี่ยน (ระดับ segment เท่านั้น — SIM-09)
- [x] unit tests: มี/ไม่มี tipping, deterministic ต่อ seed

### P5-M3 — Calibration UI (append-only) ✅ (12 ก.ค. 2026)
- [x] Backend: `GET /calibration.json` (Brier รวม + rating bands + trend รายสัปดาห์ + per-domain + รายการ prediction ครบกำหนด/ยัง)
- [x] `POST /predictions/{id}/resolve` outcome `true|partial|false` (+note) — **partial = 0.5 ใน Brier**; เขียนเป็น resolution record ใหม่ (append-only ตาม TRUST-01) ผ่าน RBAC (analyst ขึ้นไป)
- [x] หน้า Calibration: 3 stat cards (serif 4xl), sparkline เส้นอ้างอิง 0/0.25, domain rows ✓/~/✗, outcome pills, tooltip สูตรทุกจุด
- [x] ปลดล็อก resolve #161 ผ่าน UI ได้จริง
- [x] tests: partial Brier, append-only (ยิง resolve ซ้ำ = record ใหม่ไม่ทับ), RBAC

### P5-M4 — Red Team in-population + Compare ✅ (12 ก.ค. 2026)
- [x] persona factory: flag `red_team=True` → แทน 2 agents สุดท้ายด้วย contrarian (prior −0.6) + auditor (−0.3) — ไม่แตะ cap/BudgetGuard
- [x] endpoint รันคู่: baseline + red team ด้วย **seed เดียวกัน** → คืน run id คู่ + delta
- [x] หน้า Compare: delta banner (ไอคอนขึ้น/ลง/คงที่) + 2 panes + CalculationModal (breakdown per-segment + สูตร delta)
- [x] GOV-05: Red Team ให้ insight ช่องโหว่เท่านั้น ห้าม generate สารตอบโต้ | tests

### P5-M5 — Watchlist + alerts + webhook ✅ (12 ก.ค. 2026)
- [x] ตาราง PG: `watchlists` (question, domain, cadence, active, last_run_at), `alerts` (kind, payload, read_at) — ผ่าน governance store pattern เดิม
- [x] Alert 2 ชนิด: `tipping_point` (จาก M2 detector) + `consensus_shift` (เทียบ run ก่อนหน้าของคำถามเดิม |Δ| ≥ 0.1)
- [x] Webhook: POST https-only, payload `{text, content, kind, ...}` เข้ากันได้ Slack/Discord/generic, **best-effort** (พังห้ามทำ run พัง), ไม่ log URL/secret
- [x] Re-run ตาม cadence ผ่าน Celery beat — ทุกครั้งผ่าน BudgetGuard + cost estimate
- [x] หน้า Watchlist (list + toggle + Run now + alerts feed) + unread badge ที่ sidebar
- [x] tests: shift detection, webhook ไม่ยิง http://, run พังไม่กระทบ

### P5-M6 — Knowledge graph viz + Insights ✅ (12 ก.ค. 2026)
- [x] `GET /graph/summary.json`: nodes+edges จาก Neo4j + degree + hub (top 15% ไม่เกิน 6) + cluster ตาม kind
- [x] Interactive SVG แบบ studio: wedge layout ตาม cluster, hub วงแหวน, click node → side panel connections, filter chips ตาม kind
- [x] หน้า Insights: runs timeline + factor cloud + metric averages จาก registry/audit (ของเรามีข้อมูลครบอยู่แล้ว)
- [x] tests: summary endpoint (mock Neo4j), hub calculation

### P5-M7 — Persona Packs + AI-generate + ลอง ask ✅ (12 ก.ค. 2026 — ผู้ใช้สั่ง "ทำต่อ")
- [x] `simulation/persona_packs.py`: pack = ชุด segments โครงเดียวกับ segments.yaml → `PersonaFactory(segments=...)` ใช้ได้ตรงๆ; validate ครบ (share/mix รวม 1.0, priors 0-1, 2-8 segments) + **PII gate ทุกข้อความ (GOV-01, detector ปิด = fail-closed)**
- [x] `simulation/persona_ai.py`: generate จาก prompt (analyst tier + temperature 0 + retry 1 ตาม pattern judge + BudgetGuard) และ try-ask (crowd + reasoning=False + sanitize)
- [x] endpoints: GET/POST/DELETE /personas/packs, /generate (คืน preview — มนุษย์ตรวจก่อนบันทึก), /try-ask | dashboard.json + compare.json รับ `pack_id`
- [x] UI: preset cards ใน wizard (สำมะโน default + packs) + PersonaPackModal (prompt → preview → ลอง ask ราย segment → save)
- [x] tests +15 (mock LLM ทั้งหมด — ไม่เผางบจริง): PII block, fail-closed, normalize share, retry, factory sampling, endpoint cycle

### P5-M8 — Public Gallery + agree/disagree votes ✅ (12 ก.ค. 2026 — GOV review เป็น ADR-0004, ผู้ใช้ veto ได้)
- [x] `governance/gallery.py`: guard_share fail-closed 4 ด่าน (**election ห้ามแชร์เด็ดขาด** — เข้มกว่า GOV-02 ปกติ, แชร์=export ต้อง EXPORT+watermark เปิด, PII gate หัวข้อ, detector ปิด=ปฏิเสธ)
- [x] snapshot frozen (NFR-07): payload ถ่ายสำเนา ณ เวลาแชร์ แก้ไม่ได้ ถอนได้อย่างเดียว (record คงอยู่) + audit ทุกแชร์/ถอน (GOV-04)
- [x] votes ไม่เก็บตัวตน: sha256(salt|ip|ua) ทางเดียว, 1 hash = 1 เสียง (โหวตซ้ำ=เปลี่ยนเสียง), rate limit 429
- [x] endpoints: POST /gallery/share (EXPORT), GET /gallery.json + /{token}.json + vote (สาธารณะ — precedent citizen), DELETE (EXPORT)
- [x] UI: หน้า Gallery (disclaimer ถาวร + crowd vs swarm + โหวต) + ปุ่มเผยแพร่ใน dashboard tab รายงาน
- [x] tests +10 | ADR-0004 บันทึกทุกการตัดสินใจ governance

## Backlog (ยังไม่เริ่ม — ต้องมติผู้ใช้/GOV review)

- MCP tools surface (create-run/get-run) — ต้องผ่าน auth/RBAC

## สถานะ

| M | สถานะ |
|---|---|
| M1 UI shell | ✅ 12 ก.ค. |
| M2 Tipping + canvas | ✅ 12 ก.ค. |
| M3 Calibration UI | ✅ 12 ก.ค. |
| M4 Red Team + Compare | ✅ 12 ก.ค. |
| M5 Watchlist + webhook | ✅ 12 ก.ค. |
| M6 Graph viz + Insights | ✅ 12 ก.ค. |
| M7 Persona packs + AI | ✅ 12 ก.ค. |
| M8 Public gallery + votes | ✅ 12 ก.ค. |

## สรุปปิด Phase 5 (12 ก.ค. 2026) — ครบทุก milestone M1..M6 ในวันเดียว

UI ยึด studio ครบ (sidebar+badge, header pattern, tabs, tooltip-สูตรทุก metric) +
หน้าใหม่ 4 หน้า (Compare / Calibration / Watchlist / Insights) + engine เพิ่ม
tipping detection (ปิดข้อบังคับ PRD ขั้น 7 ที่ตกหล่น), Red Team in-population,
watchlist retention loop + webhook | tests 268 เขียว (M7 เพิ่มทีหลังปิดเฟส) | จุดต่างจาก SwarmSight ที่รักษาไว้:
ทุกอย่าง seed-deterministic, resolve เป็น append-only, webhook ไม่แตะ secret, PII/GOV ครบ
