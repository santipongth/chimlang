# SwarmSight Research v2 — วิเคราะห์ลึกเพื่อประยุกต์เข้าชิมลาง (UI ยึด studio)

> วันที่: 12 ก.ค. 2026 | รอบสอง (ผู้ใช้สั่ง research ใหม่ โฟกัส: ออกแบบ UI ตาม https://swarm-visionary-forge.lovable.app/studio + นำ features/algorithm/techniques/architecture/mechanism มาปิด gap ของชิมลาง)
> แหล่ง: clone `.tmp/swarm-visionary-forge` (commit `db25f13` — มี FEATURES.md ที่เจ้าของเขียนสรุปครบ 17 ฟีเจอร์) — อ่านโค้ดจริงทุกไฟล์สำคัญ ไม่ใช่แค่เอกสาร

---

## 1. สิ่งที่เปลี่ยนจาก research รอบแรก (repo อัปเดตใหญ่)

รอบก่อนเห็นแค่ debate loop + Red Team + metrics ตอนนี้ repo เพิ่ม:

- **Engine ใหม่ `graph_swarm`** — mini-GraphRAG ครบวงจร: ingest (file/URL/RSS) → chunk → embed → entity/edge extraction → retrieval ป้อน agent
- **Plugin architecture**: `SimulationEngine` interface + registry — 3 engines (lovable, mirofish adapter, graph_swarm) เสียบสลับได้โดย UI ไม่รู้จัก provider
- **Retention loop เต็มวงจร**: watchlist (subscribe คำถาม, cadence daily/weekly) → alert 2 ชนิด (tipping_point, consensus_shift ≥10 จุด) → webhook Slack/Discord + realtime toast + weekly digest cron
- **Calibration UI สมบูรณ์**: mark outcome 3 ค่า → Brier + trend sparkline รายสัปดาห์ (เส้นอ้างอิง 0 / 0.25) + per-domain breakdown
- **Compare mode**: รัน baseline + Red Team คู่ขนานในคลิกเดียว → หน้าเทียบ delta + CalculationModal (per-persona breakdown)
- **Persona packs**: AI-generate จาก prompt (2–8 ตัว, Zod schema), single-persona simulator ("ลอง ask" ก่อนรันเต็ม), custom preset เก็บใน settings
- **Growth surface**: share token, public gallery, agree/disagree votes, fork (?fork= prefill), MCP tools (create-run/get-run/list-runs)

## 2. กายวิภาค engine (อ่านจากโค้ดจริง)

### 2.1 Debate loop (`engines/graph-swarm/index.ts`)
- 3 rounds คงที่, ทุก round ทุก agent โพสต์พร้อมกัน (`Promise.all`)
- แต่ละ agent เห็น: persona ของตัวเอง + stance ปัจจุบัน + top-6 chunks จาก retrieval + **สุ่ม 6 โพสต์จาก round ก่อน** (REPLY_SAMPLE=6) + BREAKING event ถ้ามี inject
- Output บังคับ JSON `{content ≤60 คำ, stance ∈[-1,1], sentiment ∈[-1,1]}` — clamp เสมอ
- Synthesis ตอนจบ: LLM สรุป + มี **fallback แบบกลไก** (นับ bull/bear/neutral จาก stance) ถ้า LLM พัง — pattern "อย่าให้รันทั้งอันตายเพราะ call เดียว"
- `onAgent` callback ต่อ agent → UI stream progress ได้แบบ realtime

### 2.2 Ingestion (`graph-swarm-ingest.server.ts`)
- chunk 800 ตัวอักษร overlap 100 → embed batch 50 (gemini-embedding-001, 3072 มิติ) → เก็บ JSON
- Entity extraction: LLM call เดียวบน **5 chunks แรกเท่านั้น** → entities+edges (Zod) → upsert
- Retrieval: brute-force cosine ใน JS เหนือ ≤500 chunks (ยอมรับตรงๆ ว่า MVP)
- ทุก source มี status machine: pending → ready/empty/error + orphan file cleanup เมื่อรันพัง

### 2.3 Metrics (`metrics.ts`) — กลไกล้วน $0 ทุกตัว
| ชื่อ | สูตร | ของเรา (SIG-01) มีไหม |
|---|---|---|
| narrative_momentum | Σ|Δ avg stance ระหว่าง round| / (rounds−1) | ✅ มี |
| narrative_dispersion | stddev stance round สุดท้าย | ✅ มี |
| bullish_shift | Δ สัดส่วน stance>0.2 (แรก→สุดท้าย) | ✅ มี |
| **consensus_fragility** | dispersion×0.6 + late-momentum×0.4 | มี (สูตรต่าง) — ของเขาเป็น **proxy กลไกฟรีระหว่างรัน** เทียบของเรา (multi-universe flip rate — แม่นกว่าแต่แพง) |
| sentiment_divergence | stddev sentiment round สุดท้าย | ✅ มี (voice vs population) |
| **interpretation_gap** | mean|stance − sentiment|/2 — "อ่านข้อมูลเดียวกัน สรุปคนละทาง" | ⚠️ PRD SIG-01 ระบุ Event Interpretation Gap — ของเขาให้สูตรที่ใช้ได้เลย |
| **contrarian_pressure** | สัดส่วน agent มั่นใจสูง (|stance|>0.5) ที่สวนเสียงข้างมาก | ⚠️ อยู่ในรายการ SIG-01 — สูตรนี้ตรงและถูก |
| tipping_points | round ที่ avg stance กระโดด ≥0.25 → เก็บ meta.points | ❌ **เราไม่มี tipping detection อัตโนมัติ** ทั้งที่ PRD บังคับ "Tipping Points เป็น output บังคับของทุกรายงาน" (pipeline ขั้น 7) |

### 2.4 Injectable event (`round.server.ts`)
- Inject = **รอบพิเศษต่อท้าย** run เดิม (ไม่ fork): upsert `run_rounds.injected_event` เป็น provenance, re-retrieve chunks ด้วยข้อความ event, agent ทุกตัว react, recompute metrics ทั้งชุด, **ยิง alert อัตโนมัติถ้าเกิด tipping**
- รองรับ `personaOverride` เฉพาะรอบ inject (เช่น "ถ้าข่าวนี้ไปถึงกลุ่ม X ก่อน")
- ของเรา (SIM-04) fork สอง branch ด้วย seed เดียวกัน — **แข็งแรงกว่าเชิงวิทยาศาสตร์** แต่ไม่มี "inject แล้วดูต่อทันที + alert" แบบ interactive

### 2.5 Red Team mechanism (`personas.ts`)
- `_redTeam` flag ใน persona_mix → **แทนที่ 2 slots สุดท้าย** ด้วย contrarian (stance_prior −0.6, "consensus is usually wrong at the top") + auditor (−0.3, "assumes evidence is cherry-picked")
- Compare mode = สร้าง 2 runs พร้อมกัน (baseline, +RedTeam) → `/compare?a=&b=` → delta banner + CalculationModal แจกแจงต่อ persona
- **ต่างจาก REH-02 ของเรา**: ของเรา Red Team เป็น swarm แยกที่ผลิต Attack Surface Report; ของเขา Red Team **ฝังใน population แล้ววัดผลต่อ consensus เป็นตัวเลข** (quantified groupthink test) — เสริมกันได้ ไม่ทับกัน

### 2.6 Retention loop (swarm.functions.ts + watchlist.functions.ts)
- จบ run: (1) มี tipping → insert alert + fire webhook (2) คำถามตรงกับ watchlist active → เทียบ confidence กับ run ก่อนหน้าของคำถามเดียวกัน, |Δ|≥0.1 → alert `consensus_shift` + webhook
- Webhook: POST https-only, ส่ง `{text, content, ...}` ให้เข้ากันทั้ง Slack/Discord/generic, **best-effort — webhook พังห้ามทำ run พัง**
- UI: supabase realtime → toast ทันที + unread badge ที่ sidebar

### 2.7 Calibration (`getCalibration` + calibration.tsx)
- Outcome enum: happened=1 / **partial=0.5** / didnt=0 → Brier = mean (confidence − y)²
- Rating bands: <0.1 ยอดเยี่ยม, <0.2 ดี, <0.3 พอใช้, ≥0.3 ต้องปรับปรุง
- Trend: bucket รายสัปดาห์ + sparkline SVG มือเปล่า มี**เส้นอ้างอิง 0 (perfect) และ 0.25 (โยนเหรียญ)** + tooltip อธิบายสูตรทุกจุด
- ⚠️ จุดอ่อนเขา: outcome เป็น UPDATE บน runs — **แก้ย้อนหลังได้** (ขัด TRUST-01 ของเรา — เวลา port ต้องเขียนเป็น resolution record append-only)

## 3. จุดอ่อนของ SwarmSight ที่ห้ามเลียนแบบ (ยืนยันจากโค้ดรอบนี้)

1. `Math.random()` ทุกจุด sampling — **ไม่มี seed, reproduce ไม่ได้** (ขัด NFR-07 เรา)
2. Outcome/calibration แก้ย้อนหลังได้ (ขัด TRUST-01) — ของเราต้อง append-only resolution เสมอ
3. ไม่มี cost estimate / budget guard ใดๆ (ขัด BudgetGuard บังคับของเรา)
4. ไม่มี PII gate / governance ใดๆ ใน ingest (URL/RSS/file เข้า DB ตรงๆ — ขัด GOV-01)
5. `genPost` fail → คืน `stance 0 + "(agent failed to respond)"` แล้ว**นับต่อใน metrics** — silent corruption; ของเราต้อง fail-closed หรือติดธง
6. Agent confidence เป็นสูตร ad-hoc (`0.4 + |stance|×0.5`) ไม่ได้มาจากการวัด
7. Entity extraction จาก 5 chunks แรกเท่านั้น + retrieval brute-force — ไม่ scale (เรามี Neo4j + provenance ครบ ดีกว่ามาก)

## 4. Gap analysis — อะไรที่คุ้มเอาเข้าชิมลาง (เรียงตาม impact ÷ effort)

ชิมลางแข็งกว่าอยู่แล้ว: governance ทุกด่าน, seed determinism, hindcast/leak test, Neo4j GraphRAG + provenance, watermark, scale 1,000 agents, Thai fabric 4 channels, silent majority ฯลฯ — **สิ่งที่ SwarmSight มีแล้วเราไม่มี เกือบทั้งหมดอยู่ชั้น UX/retention ไม่ใช่ชั้น trust**:

| # | ของเขา | ปิด gap อะไรของเรา | Effort |
|---|---|---|---|
| G1 | **Calibration UI** (mark outcome 3 ค่า + Brier trend + per-domain) | **งานค้างอันดับ 1 ใน STATE**: prediction #161 ค้าง resolve เพราะต้องใช้ CLI — UI จะทำให้ผู้ใช้ป้อน outcome เองได้ ปลดล็อก calibration แท้จริง; เพิ่ม `partial=0.5` ที่ระบบเรายังไม่มี | S |
| G2 | **Tipping point detection** (Δavg ≥0.25/round → meta.points + alert) | PRD บังคับ "Tipping Points ใน**ทุก**รายงาน" (pipeline ขั้น 7) — เรายังไม่มี detector อัตโนมัติ | XS |
| G3 | **Watchlist + consensus_shift alert + webhook** | REH-05 เรามี alarm ใน war room แต่ไม่มี subscription loop (ติดตามคำถามเดิมซ้ำตาม cadence) + ไม่มี webhook delivery — นี่คือ retention mechanism ที่ทำให้ระบบถูกใช้ต่อเนื่อง | M |
| G4 | **Red Team in-population + Compare view** | REH-02 เราให้ report; ของเขาให้ **ตัวเลข delta ต่อ consensus** = วัด groupthink ได้จริง — เพิ่มใน engine เราถูกมาก (สลับ 2 personas ด้วย adversarial priors + รัน 2 runs seed เดียวกัน) | S–M |
| G5 | **หน้า Compare + CalculationModal** (per-segment breakdown, tooltip สูตรทุกจุด) | DASH-03 เรามีตารางใน dashboard เดียว — side-by-side view + "คณิตโปร่งใส inline" ตรง TRUST-09/NFR-08 พอดี | M |
| G6 | **Persona packs + AI-generate + ลอง ask** | เราสร้าง persona จาก census (แม่นกว่า) แต่ไม่มีทางให้ผู้ใช้นิยาม audience เอง/reuse; "ลอง ask 1 คำตอบ" = preview ราคาถูก (ใช้ `reasoning=False` path ที่เรามีอยู่) ก่อนเผнегงบรันเต็ม | M |
| G7 | **Knowledge graph viz แบบ interactive** (cluster wedge + hub top-15% degree + click → side panel connections) | เรามี Neo4j + `/graph/indirect.json` แต่ไม่มี visualization เลย — SIM-09 Hub Nodes/Cluster Map ของ PRD ยังไม่มีหน้าจอ | M |
| G8 | **Opinion swarm canvas** (scatter: x=stance, y=confidence, สี=ทิศ, คลิก=drill-down) | DASH-04 เราแสดง voices เป็นข้อความ — scatter นี้ทำให้เห็น dispersion/คลัสเตอร์ในพริบตา (agent จำลองเท่านั้น ไม่ map บุคคลจริง — ผ่าน SIM-09) | S |
| G9 | **Insights ข้าม run** (factor cloud จาก cited_factors, confidence timeline, metric averages) | เรามี registry + audit ครบแต่ไม่เคย aggregate ข้าม run ให้ดู | M |
| G10 | **Engine registry pattern + onAgent streaming** | เตรียมทางให้ debate engine (โหมดใหม่) อยู่ร่วมกับ round-based engine เดิม + progress bar จริงตอนรัน | S |
| G11 | Template gallery ใน wizard + onboarding tour + fork | UX polish — เรามี chips อยู่แล้ว ขยับเป็น card gallery แบบ studio | XS |
| G12 | MCP tools (create-run/get-run/list-runs) | เปิดชิมลางให้ agent ภายนอกเรียกได้ — future, ต้องผ่าน auth/RBAC เรา | backlog |
| G13 | Public gallery + votes (wisdom-of-crowds vs swarm) | น่าสนใจแต่ต้อง GOV review (GOV-02 aggregate-only + watermark ทุก export) | backlog |

**ที่ไม่เอา**: brute-force retrieval (เรามี Neo4j), outcome mutable, Math.random, ไม่มี budget guard, Supabase/Lovable stack (เรา FastAPI+PG ตาม D1/D6)

## 5. UI Design Spec — ยึด studio (แกะจากโค้ดจริง ไม่ใช่ตาดู)

### 5.1 Design tokens (styles.css ของเขา vs index.css เรา)
- **สีตรงกันอยู่แล้วเกือบ 100%** (เพราะ theme เราแกะจาก ref เดียวกันตอน P4-M1): background `oklch(0.99 0.003 240)`, primary `oklch(0.7 0.15 160)`, border `oklch(0.92 0.008 240)`, radius 0.75rem
- ที่เราขาดและควรเพิ่ม: `--color-sidebar-accent` (hover/active nav), `--color-ring`, `--color-chart-1..5` (`160/240/80/30/300`), popover, dark-mode block (`.dark`)
- ฟอนต์เขา: heading = **Instrument Serif**, body = Inter → ของเรา (ไทย first-class): heading = Noto Serif Thai/Sarabun serif fallback ตามที่มี, body = Noto Sans Thai — คง letter-spacing -0.01em ที่ h1-h3

### 5.2 Layout กติกากลาง
- **Sidebar ซ้าย w-60 (240px)** `bg-sidebar border-r p-4` + main `flex-1 min-w-0` (มือถือซ่อน sidebar)
- Nav item: `flex items-center gap-2 rounded-lg px-3 py-2 text-sm` + icon 16px, active = `bg-sidebar-accent`, **unread badge** วงกลม primary ตัวเลขขาวชิดขวา
- Logo: icon ใน `h-8 w-8 rounded-lg bg-primary/10 text-primary` + ชื่อแบรนด์ font-serif
- Content container: `mx-auto max-w-3xl px-6 py-10` (ฟอร์ม/wizard) หรือ `max-w-4xl` (dashboard/list)
- **Page header pattern** (ทุกหน้า): eyebrow (`text-xs uppercase tracking-wider text-muted-foreground` + icon primary 12px) → `font-serif text-4xl` → คำอธิบาย `text-sm text-muted-foreground max-w-2xl`
- Card: `rounded-2xl border bg-card p-5..6`; ตัวเลขใหญ่ = `font-serif text-4xl`
- Selection card (ทุก picker): `rounded-lg border p-3 text-left`, เลือกแล้ว = `border-primary bg-primary/5`
- Stepper: วงกลมเลข `h-6 w-6 rounded-full border` (active เต็ม primary, ผ่านแล้ว `border-primary/40 bg-primary/10 text-primary`) คั่น ChevronRight; สลับ step ด้วย motion `opacity+x:8px`
- Toggle-card pattern: Red Team ใช้โทน destructive (`border-destructive/50 bg-destructive/5` + pill "ON"), A/B ใช้โทน primary
- Time-range filter: segmented pill `inline-flex rounded-lg border bg-card p-1` ปุ่ม active `bg-primary text-primary-foreground`
- **กฎเหล็ก tooltip**: metric ทุกตัว (Brier, confidence, delta, fragility) มี Info icon + อธิบายสูตร inline — ตรงปรัชญา TRUST-09 เราพอดี ให้บังคับเป็น convention ของ web/ ด้วย

### 5.3 โครงหน้า (mapping เข้า 5 หน้าเดิม + หน้าใหม่)
| หน้า | ยึดจาก studio | หมายเหตุ governance |
|---|---|---|
| **รันใหม่ (wizard)** | stepper 4–5 ขั้นแบบ studio: คำถาม+template gallery cards → engine picker (3 cards) → **Sources (upload/URL/RSS)** → agents (slider+mix+Red Team toggle+A/B toggle+persona preset cards+ปุ่ม AI-generate) → review | Sources ทุกชิ้น**ผ่าน PII detector ก่อน ingest** (GOV-01) — ต่างจากเขาที่รับตรง |
| **Dashboard/run detail** | tabs `debate / canvas / report` ใต้ header + ปุ่ม inject event (modal) + mark outcome pills บน header + export | watermark banner คงเดิม, election 403 คงเดิม |
| **Compare (ใหม่)** | delta banner + 2 panes + CalculationModal | ตัวเลขทุกตัวมีช่วง (TRUST-09) |
| **Calibration (ใหม่)** | 3 stat cards + sparkline (เส้น 0/0.25) + domain rows + รายการ mark outcome | เขียนเป็น resolution append-only ห้าม UPDATE |
| **Watchlist (ใหม่)** | list + toggle active + Run now + alerts feed + webhook setting | ผ่าน BudgetGuard ทุกครั้งที่ re-run |
| **การจัดการรัน (เดิม)** | ปรับ list style เป็น card pattern เดียวกัน | — |
| **Citizen (เดิม)** | คง disclaimer ถาวร ปรับ header pattern | CIT-04 |

## 6. ข้อเสนอแผน Phase 5 (ปรับจากร่างรอบก่อนให้ตรง focus นี้ — **รอผู้ใช้ approve ก่อนเริ่ม**)

| M | ขอบเขต | ขนาด |
|---|---|---|
| M1 | **UI shell ตาม studio**: token เพิ่ม (sidebar-accent/chart/ring/dark), sidebar nav ใหม่ + badge, page header pattern, wizard 5 ขั้น (รวม Sources ผ่าน PII gate + template gallery + Red Team/A-B toggles), tabs ใน dashboard | L |
| M2 | **Tipping detection + metrics เก็บตก** (interpretation_gap, contrarian_pressure ถ้าขาด) เข้า engine + บังคับใน report ทุกฉบับ (ตาม PRD ขั้น 7) + opinion swarm canvas | S |
| M3 | **Calibration UI**: mark outcome happened/partial/didnt → append-only resolution + Brier partial=0.5 + trend sparkline + per-domain — ปลดล็อก resolve #161 และ predictions ถัดไป | M |
| M4 | **Red Team in-population + Compare**: `_red_team` ใน persona factory (2 adversarial priors) + รันคู่ seed เดียวกัน + หน้า compare + CalculationModal | M |
| M5 | **Watchlist + alerts + webhook**: Celery beat ตาม cadence, consensus_shift (Δconfidence ≥ threshold), tipping alert, webhook https POST (best-effort + ไม่ log secret) | M |
| M6 | **Knowledge graph viz** (Neo4j → hub/cluster interactive) + **Insights ข้าม run** (factor cloud, timeline จาก registry/audit) | M |
| backlog | Persona packs + AI-generate + ลอง ask, MCP surface, public gallery + votes (ต้อง GOV review) | — |

ทุก milestone: seed determinism + BudgetGuard + governance เดิมครบ, test คู่ทุก module, ไทย first-class

---
*ไฟล์ clone อยู่ `.tmp/swarm-visionary-forge` (disposable) — รายงานรอบแรกดูบันทึกส่งมอบ 12 ก.ค. ใน STATE.md*
