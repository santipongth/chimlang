# ADR-0014: Pilot-ready trust contract และ productized workflow

- สถานะ: Accepted (17 ก.ค. 2026 — ผู้ใช้ส่ง roadmap Phase 9 และสั่งให้ implement)

## บริบท

Phase 8 ทำให้ runtime, prediction contract, retrieval, experiment และ observability แข็งแรงขึ้น
แต่คำว่า reproducible ยังอาศัยเพียง `run_id + seed` ขณะที่ persona, evidence, prompt, model,
pricing และ engine configuration ไม่ได้ถูก freeze เป็น contract เดียว นอกจากนี้ lifecycle update
ยังมีโอกาสแข่งกับ cancel, async endpoint ยังผูก UI กับ Celery job, external fetch ยังตรวจ SSRF
ไม่ครบ DNS/redirect และ hash router เขียนเองไม่รู้จัก deep link ทุกชนิด

ความเสี่ยงเหล่านี้กระทบความน่าเชื่อถือของ pilot มากกว่าการเพิ่ม simulation engine จึงเปิด Phase 9
โดยให้ Trusted Run Foundation เป็น milestone gate ก่อน Project/Evidence/Validation Lab และ Rehearsal UI

## การตัดสินใจ

1. ทุก run ใหม่มี immutable `RunSpecV1` และ append-only `RunManifestV1` แบบ 1:1 กับ run
   - spec เก็บ normalized request, seed และ persona snapshot
   - manifest เก็บ evidence/news/posts/result snapshots, prompt/model/adapter/engine/git/pricing
     version, governance decisions, artifact hashes และ `config_hash`
   - hash ใช้ SHA-256 ของ canonical JSON (UTF-8, key sort, compact separators) โดยไม่รวม
     timestamp/ตัว hash เอง
2. run เก่า backfillเฉพาะ manifest `schema_version=0`, `complete=false`,
   `reproducibility=legacy-incomplete`; ห้ามสร้าง provenance ย้อนหลังจากการเดา
3. provider determinism เป็น best-effort จึงใช้คำว่า “รันใหม่ด้วย input ที่ freeze” ไม่ใช้
   “exact replay” และแยกจาก “รันด้วยข้อมูลล่าสุด” กับ “เปิด snapshot ผลเดิม” อย่างชัดเจน
4. lifecycle เป็น compare-and-set เท่านั้น: `queued -> running -> complete|error|canceled`;
   terminal state เขียนทับไม่ได้ และ worker ตรวจ cancellation ก่อน/หลังทุก stage กับก่อน persist
   post/result/finding/manifest
5. `POST /runs/async` รับ `Idempotency-Key`, ตอบ `202 Accepted` ทันทีพร้อม URL ของ status,
   events, manifest และ snapshot; key เดิม+request hash เดิมคืน run เดิม ส่วน key เดิม+payloadต่าง
   ตอบ conflict
6. external HTTP/RSS ใช้ `SafeOutboundFetcher` กลางเท่านั้น: http(s), no credentials,
   resolve A/AAAA, อนุญาตเฉพาะ global address, ตรวจ redirect ทุก hop, จำกัด hop/content type/
   compressed และ decompressed body และ fail closed เมื่อ resolve/validation ไม่ครบ
7. frontend ใช้ React Router `HashRouter` เพื่อคง deployment ใต้ `/app/`; route/run/gallery/
   experiment เป็น typed route tree มี not-found และ mobile navigation ทดแทน sidebar
8. export ของ stored run มี JSON และ PDF สำหรับทุก engine โดยอ่าน snapshot ที่บันทึกแล้วเท่านั้น
   ทุก format ผ่าน watermark contract และแนบ manifest/config hash; export ห้ามเรียก simulation/LLM/network
9. API ใหม่เป็น additive; endpoint เดิมและ MCP behavior คง compatibility ระหว่าง migration
10. Phase 9 M1 เป็น trust gate: ต้องรายงาน migration, concurrency/SSRF tests และ UX screenshots
    แล้วหยุดรอมติผู้ใช้ก่อนเริ่ม M2

## ผลกระทบ

- เพิ่ม migration append-only `run_manifests`; operational run ยังลบได้ แต่ manifest คงอยู่เพื่อ audit
- trust score ให้ reproducibility ผ่านเฉพาะ manifest V1 ที่ครบและ hash ตรวจสอบได้
- live-news rerun แบบ frozen ไม่แตะ network; mode latest จึงอนุญาต external fetch ตาม governance
- Phase 9 ไม่เปลี่ยน cap 1,000 agents, `$5/run`, `$50/month`, LLM adapter หรือ public-GA
  architecture ที่ deferred ใน ADR-0012

## แนวคิดมาตรฐานที่ใช้

- W3C PROV: entity/activity/derivation/versioning เป็น conceptual mapping ของ manifest
- RFC 9110: `202 Accepted` สำหรับงาน async ที่ยังไม่เสร็จ
- OWASP SSRF Prevention: validate destination และ redirect แบบ fail-closed
- NIST AI RMF GenAI Profile: TEVV และหลักฐานตรวจสอบได้ตลอด lifecycle
