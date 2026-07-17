# P9 — Production-real runtime gate

วันที่ทดสอบ: 17 ก.ค. 2026
ขอบเขต: self-hosted single-tenant trusted network ตาม ADR-0012/0018

## สิ่งที่ปิดแล้ว

- Compose supervise API, Celery worker และ beat พร้อม auto-restart, migration dependency และ health checks
- readiness ตรวจ PostgreSQL/Redis/Neo4j + worker heartbeat และ Celery control ping
- append-only PopulationSetV1; synthetic set ต้องรับทราบและ run manifest อ้าง immutable hash
- Citizen portal/impact/feedback ถูกถอดจาก production routes (ทั้งหมดตอบ 404) และย้าย demo เป็น offline CLI
- analyst synthesis failure ทำให้ Debate run เป็น error โดยไม่สร้าง mechanical success fallback
- CI แยก backend mocked, browser stubbed, live real-process และ manual paid-provider smoke

## หลักฐาน process จริง

รันใน Compose project แยกพอร์ต/volume แล้วลบ environment ชั่วคราวหลังทดสอบ:

1. startup readiness: postgres=ok, redis=ok, worker=ok, neo4j=ok
2. unmocked Fabric workflow:
   - Project → text Evidence → immutable EvidenceSetV1 → acknowledged PopulationSetV1
   - POST /runs/async ตอบ 202 → Celery worker → complete → stored JSON export
   - run fabric-20260717-160433-272386-c1d31657
   - manifest 88dea75beda4b3645a9d035aa9e825355c5bd1f0fadbd386303a1dabef5fbee0
3. supervisor recovery:
   - ฆ่า Celery child process ทำให้ Docker restart count เปลี่ยน 0 → 1
   - หยุด worker แล้ว /health/deep รายงาน degraded, worker=offline
   - เปิด worker แล้ว startup gate กลับ ok
4. OpenRouter Debate smoke ภายใต้ BudgetGuard:
   - 2 agents × 1 round, BM25 retrieval
   - estimate USD 0.000775; actual adapter spend USD 0.000411 ต่ำกว่า smoke cap USD 0.05
   - run debate-20260717-163447-398548-e2c7628d
   - manifest 0a59887a9f2f158178dbbe4c4aed9136f6257e5e48f5c5843b87d377bfda5c89
   - result และ stored export complete; ไม่มี mock/stub ใน HTTP, queue, database หรือ provider path

ทั้งสอง live runs อยู่ใน isolated disposable database และถูกลบพร้อม volume หลังจบ จึงไม่ปะปนกับข้อมูลหลัก

## Regression/contract gates

- backend: 427 collected tests ผ่าน; Ruff check/format ผ่าน; migration no-op
- frontend: Vitest 8/8, production build ผ่าน, initial index 93.14 kB (ยังอยู่ใน +15% gate)
- browser-stubbed: Playwright 26/26 desktop/mobile รวม axe WCAG และ Population acknowledgement flow
- production dependency audit: 0 vulnerabilities
- main runtime พอร์ต 8000: Compose services healthy ครบ, /projects เข้าถึงได้, Citizen routes ทั้งหมด 404,
  ไม่มี host uvicorn/celery process ซ้ำ

## ข้อจำกัดที่ยังต้องพูดตรง ๆ

- usability gate ยังไม่ปิดจนมีผู้ใช้ไทยจริง P01–P05 ครบ 5 คนและ 25 task records ที่ consent แล้ว
- Public GA/TLS/OIDC/RLS, pen-test, backup/DR และ SLO ยัง deferred; ผลนี้ไม่ใช่การรับรอง Public GA
- synthetic PopulationSet เป็นสมมติฐาน ไม่ใช่ผลสำรวจ/สำมะโน แม้จะ freeze และ trace ได้แล้ว
