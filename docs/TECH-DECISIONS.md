# TECH DECISIONS — ชิมลาง (CHIMLANG)

เอกสารการตัดสินใจทางเทคนิคก่อนเริ่ม Phase 0 — **ติ๊กเลือกในแต่ละข้อ** แล้ว Claude Code จะยึดตามนี้
ทุกข้อมี "คำแนะนำเริ่มต้น" ที่เลือกให้แล้ว ถ้าไม่แน่ใจให้ใช้ตามนั้นได้เลย หรือสั่ง Claude Code วิเคราะห์ trade-off เพิ่มก่อนตัดสินใจ

สถานะ: 🔲 = ยังไม่ตัดสินใจ | ✅ = ตัดสินใจแล้ว

---

## D1 — ภาษาและ framework ฝั่ง backend

| ตัวเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **Python 3.12 + FastAPI** ⭐ แนะนำ | ecosystem AI/LLM ครบที่สุด, CAMEL-AI OASIS เป็น Python, หาคนไทยทำได้ง่าย | ช้ากว่า Go/Node ในงาน I/O หนัก (แก้ได้ด้วย async + queue) |
| TypeScript + NestJS | type-safety, ทีม frontend ใช้ภาษาเดียวกัน | ต้อง bridge ไปหา OASIS/GraphRAG ที่เป็น Python อยู่ดี |
| Go | performance, deployment ง่าย | ecosystem AI บาง, พัฒนา simulation ช้ากว่ามาก |

- [x] ตัดสินใจ: ✅ Python 3.12 + FastAPI (ตาม default) — ตัดสินใจ 5 ก.ค. 2026

## D2 — Agent runtime

| ตัวเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **ต่อยอด CAMEL-AI OASIS** ⭐ แนะนำ | ตรงตาม PRD, รองรับ agent จำนวนมาก, มี community | ต้อง custom ชั้น Thai Social Fabric เองทั้งหมด |
| Fork MiroFish | ได้ pipeline ครบเร็ว (GraphRAG→OASIS→report) | ผูกกับ design เดิม, ต้องรื้อส่วน Twitter/Reddit ออกอยู่ดี — ตรวจ license ก่อน |
| เขียน runtime เอง | ควบคุมได้ 100%, เบา | ช้ากว่าหลายเดือน, เสี่ยง reinvent สิ่งที่ OASIS แก้ไปแล้ว |

- [x] ตัดสินใจ: ✅ **แก้ไข 5 ก.ค. 2026 (ADR-0002, มติผู้ใช้)**: Phase 0 ใช้ runtime เบาของเราเองใน `simulation/` (ผล spike: OASIS ลาก torch หลาย GB + API รอบ Twitter/Reddit ขณะที่ของที่ต้องใช้ต้อง custom หมดอยู่ดี) — OASIS/MiroFish เป็น reference design; ประเมิน OASIS ใหม่เมื่อ Phase 1 ต้อง scale เกินหลักพัน

## D3 — Knowledge graph และ GraphRAG

| ตัวเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **Neo4j (Community) + custom GraphRAG pipeline** ⭐ แนะนำ | Cypher query ทรงพลัง, visualization ในตัว, เอกสารเยอะ | ต้อง host เอง, license ต้องตรวจถ้า scale เชิงพาณิชย์ |
| PostgreSQL + Apache AGE | ลด infra เหลือ DB เดียว | ecosystem เล็กกว่า, query ซับซ้อนเขียนยากกว่า |
| Microsoft GraphRAG library ตรงๆ | pipeline สำเร็จรูป | ออกแบบมาเพื่อ QA มากกว่า simulation, ปรับแต่งยาก |

- [x] ตัดสินใจ: ✅ Neo4j (Community) + custom GraphRAG pipeline, ยืม indexing pattern จาก MS GraphRAG (ตาม default)

## D4 — Long-term memory ของ agent

| ตัวเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| Zep (managed) — ตามสถาปัตยกรรม PRD | ตรง spec, temporal knowledge graph ในตัว, เร็วสุดในการเริ่ม | ข้อมูลออกนอกประเทศ — ต้องเช็ค data residency (NFR-04) กับลูกค้าภาครัฐ |
| **pgvector + memory schema เอง** ⭐ แนะนำสำหรับ Phase 0 | ควบคุม residency ได้, ไม่เพิ่ม vendor | ต้องสร้าง memory consolidation logic เอง |
| Letta / mem0 | มี memory management ระดับสูง | เพิ่ม dependency ที่ยังเปลี่ยนเร็ว |

- [x] ตัดสินใจ: ✅ pgvector + memory schema เอง ใน Phase 0, ออกแบบ interface ให้สลับเป็น Zep-compatible ได้ภายหลัง (ตาม default)

## D5 — กลยุทธ์ LLM (ต้นทุนคือความเสี่ยงอันดับต้น)

| ตัวเลือก | ข้อดี | ข้อเสีย |
|---|---|---|
| **Tiered models** ⭐ แนะนำ: model เล็ก/ถูกสำหรับ crowd agents + model ใหญ่สำหรับ analyst agent และ report | คุมต้นทุนต่อ Standard run ≤ $50 ได้จริง (NFR-02) | ต้อง benchmark ภาษาไทยของ model เล็กก่อนใช้ |
| Model เดียวทั้งระบบ | ง่าย, พฤติกรรมสม่ำเสมอ | แพงเกิน หรือคุณภาพ analyst ต่ำเกิน อย่างใดอย่างหนึ่ง |
| Local/open-weight ทั้งหมด | ถูกที่ scale ใหญ่, residency 100% | ต้องมี GPU infra + คุณภาพภาษาไทยต้องทดสอบหนัก |

เกณฑ์คัดเลือก model: (1) คุณภาพภาษาไทย (2) ราคา/1M token (3) รองรับ OpenAI-compatible API
- [x] ตัดสินใจ model crowd agent: ✅ Qwen flash-tier ผ่าน OpenRouter (OpenAI-compatible endpoint เดียว) — ยืนยัน model slug จริง + ผ่าน Thai mini-benchmark ใน M0 ก่อนใช้จริง (ดู docs/adr/ADR-0001)
- [x] ตัดสินใจ model analyst: ✅ Qwen max-tier ผ่าน OpenRouter — เงื่อนไขเดียวกับ crowd (benchmark ใน M0)
- [x] งบ compute ต่อเดือนช่วงพัฒนา: ✅ 50 USD (เพดานต่อ run: `RUN_BUDGET_USD_CAP=5` ตาม .env.example)

## D6 — System of record

- **แนะนำ: PostgreSQL 16 + pgvector** — เก็บ run config, prediction registry (append-only ด้วย trigger กัน UPDATE/DELETE), audit log, snapshot metadata
- [x] ตัดสินใจ: ✅ PostgreSQL 16 + pgvector (ตาม default) — prediction registry / audit log เป็น append-only ด้วย DB trigger

## D7 — Queue / orchestration สำหรับ simulation runs

| ตัวเลือก | เหมาะกับ |
|---|---|
| **Celery + Redis** ⭐ แนะนำ Phase 0 | งาน batch simulation ทั่วไป, เริ่มเร็ว |
| Temporal | workflow ยาวซับซ้อน (multi-universe + war room) — ค่อยย้ายใน Phase 2 ถ้าจำเป็น |

- [x] ตัดสินใจ: ✅ Celery + Redis (ตาม default) — ทบทวน Temporal เมื่อถึง Phase 2 ถ้า workflow ซับซ้อนขึ้นจริง

## D8 — Frontend

- **แนะนำ: React 18 + Vite + TypeScript + Tailwind** (dashboard-first ไม่ต้อง SSR) | ทางเลือก: Next.js ถ้าต้องการ Public Portal SEO ใน Phase 3 (ค่อยแยก app ตอนนั้นได้)
- [x] ตัดสินใจ: ✅ React 18 + Vite + TypeScript + Tailwind (ตาม default) — Phase 0 รายงานเป็น markdown/HTML ก่อน ยังไม่ลงแรง dashboard

## D9 — Deployment และ data residency

- Dev: docker-compose ทั้งชุด (api, worker, postgres, neo4j, redis, web)
- [ ] Cloud/region ที่ลูกค้ายอมรับ (ผูกกับ NFR-04): **เลื่อนการตัดสินใจ — ไม่ block Phase 0** (dev ใช้ docker-compose local ทั้งชุด; ตัดสินใจเมื่อมีลูกค้า pilot จริงใน Phase 1)
- [x] โดเมน/ชื่อ service ภายใน: ✅ chimlang-api, chimlang-sim, chimlang-web

## D10 — License และ open source strategy

- ยังเปิดอยู่ (Open Question ข้อ 5 ใน PRD) — ระหว่างนี้ตั้ง repo เป็น **private** และอย่า copy โค้ด GPL/AGPL เข้ามาโดยไม่บันทึกใน `docs/adr/`
- [ ] ตัดสินใจภายหลัง Phase 0

---

## วิธีใช้เอกสารนี้

1. ติ๊กและเติมค่าในทุก `[ ]` (ใช้ default ได้ทุกข้อถ้าไม่มีข้อจำกัดเฉพาะ)
2. commit ไฟล์นี้เข้า repo
3. Claude Code จะอ่านผ่าน @docs/TECH-DECISIONS.md — การเปลี่ยนการตัดสินใจภายหลังให้แก้ที่ไฟล์นี้ พร้อมเขียน ADR สั้นๆ อธิบายเหตุผล
