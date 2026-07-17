# ADR-0018 — Supervised production runtime และ production-real trust gates

วันที่: 17 ก.ค. 2026
สถานะ: Accepted (มติผู้ใช้โดยตรง)

## บริบท

เหตุการณ์ API รุ่นเก่าค้างบนพอร์ต 8000 และ worker หายทำให้ Project ตอบ 404 และ run ค้าง queued แม้
Redis ยังพร้อม แสดงว่า process แบบเปิดมือไม่มี lifecycle/readiness contract ที่เพียงพอ อีกทั้ง runtime เดิม
ยังเลือก population sample โดยไม่ freeze, Citizen route แสดงข้อมูลตัวอย่าง และ Debate เคยสร้าง mechanical
fallback เมื่อ analyst ล้มเหลว ซึ่งทำให้ข้อมูล demo/fallback เสี่ยงถูกตีความเป็นผลจริง

## มติ

1. Docker Compose เป็น canonical self-hosted runtime และ supervise api, worker, beat ด้วย
   restart: unless-stopped; migration ต้องจบและ dependency health ต้องผ่านก่อน service เริ่ม
2. startup gate ใช้ /health/deep และต้องได้ PostgreSQL, Redis, Neo4j และ worker เป็น ok ครบ
   โดย worker readiness ต้องผ่านทั้ง Redis TTL heartbeat และ Celery control ping จริง
3. production run ทุกตัวต้องอ้าง immutable PopulationSetV1; ชุดสังเคราะห์ต้องให้ผู้ใช้รับทราบก่อน freeze
   และ manifest ต้องบันทึก set/hash/source/synthetic/acknowledged แบบตรวจกลับได้
4. Citizen demo ไม่เป็น production route; เก็บเป็น offline CLI ที่ชื่อชัดเจนเท่านั้น
5. Debate ที่ analyst synthesis ล้มเหลวต้องจบเป็น error/degraded พร้อม audit posts ห้ามส่ง mechanical
   fallback เป็นผลสำเร็จปกติ การ resynthesize snapshot แบบ deterministic เดิมยังใช้ได้เฉพาะคำสั่งซ่อม
   snapshot ที่ผู้ใช้เรียกอย่างชัดเจน
6. CI แยกหลักฐานเป็น backend-unit-mocked, browser-stubbed และ live-integration; provider smoke
   เป็น manual workflow ที่ใช้ OpenRouter secret, model ใน pricing registry และ BudgetGuard cap ต่ำ

## ผลตามมา

- make dev/Compose เปิดระบบครบชุดและ fail เมื่อ readiness ไม่ครบ แทนการปล่อย API ที่ไม่มี consumer
- mocked/stubbed tests ยังอยู่เพื่อความเร็วและ fault injection แต่ไม่ถูกอ้างเป็นหลักฐาน live readiness
- ทุกการใช้ sample population มีข้อจำกัดปรากฏใน UI, request, immutable set และ run manifest
- public GA security (TLS/OIDC/RLS) ยัง deferred ตาม ADR-0012; มตินี้ทำให้ self-hosted trusted-network
  runtime เชื่อถือได้ขึ้น แต่ไม่เปลี่ยนสถานะเป็น Public GA
