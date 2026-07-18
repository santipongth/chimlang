# ADR-0027 — ถอด RSS ออกจาก evidence sources ต่อ run (กล่อง "แหล่งข้อมูลอ้างอิง")

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งถอด kind `rss` ออกจากกล่องแหล่งข้อมูลอ้างอิงใน wizard และทุกจุดที่เหลือใน codebase —
หลังงานนี้ evidence source ต่อ run เหลือ kind **text** และ **url** เท่านั้น

## บริบท

ADR-0026 ถอด RSS จากโต๊ะข่าวสด (News Desk) แล้ว แต่ระบุชัดว่า evidence sources ต่อ run
(`simulation/sources.py`) ยังรับ kind `rss` อยู่. ผู้ใช้ตัดสินใจถอดส่วนที่เหลือนี้ด้วยเพื่อ clean
production ตามแนว ADR-0019/0023/0024/0025/0026 — การแนบลิงก์เป็นหลักฐานยังทำได้ผ่าน kind `url`
(fetch + strip HTML + PII redact→re-scan เหมือนเดิม) ชั้น parse RSS แยกจึงไม่จำเป็น

## มติ

1. **`simulation/sources.py`** — ลบ `_parse_rss` และสาขา `kind == "rss"` ใน `_fetch_text`;
   ตัด `"rss"` ออกจากตาราง kind score ใน `_quality_score` (แถวประวัติมี score เก็บไว้แล้ว
   จึงไม่มีผลย้อนหลัง); เพิ่มค่าคงที่ `ALLOWED_SOURCE_KINDS = ("text", "url")` และให้
   `ingest_sources` ปฏิเสธ kind นอกรายการก่อนแตะ network/DB (fail-closed ชั้น engine).
   caps เดิมคงหมด: `MAX_SOURCES=10`, `MAX_TEXT_CHARS=2MB`, cache TTL 6 ชม., PII gate ADR-0010
2. **CHECK constraint (การตัดสินใจ)** — `run_sources.kind` มี CHECK `('text','url','rss')`;
   **คง `'rss'` ไว้ทั้งบนตารางเดิมและใน `_SCHEMA` (CREATE TABLE ใหม่)** ด้วยเหตุผล:
   (ก) แถวประวัติ `kind='rss'` เป็น audit/provenance ที่ต้องอ่านได้ต่อ (NFR-07) และ
   `CREATE TABLE IF NOT EXISTS` ไม่แตะตารางที่มีอยู่แล้วอยู่ดี;
   (ข) ถ้า `_SCHEMA` ตัด `'rss'` เฉพาะ fresh install จะได้ constraint ต่างจาก deployment เดิม =
   schema divergence โดยไม่ได้ประโยชน์ เพราะด่านกันเขียนจริงคือ API validation (422) +
   `ingest_sources` (ValueError) ไม่ใช่ DB constraint. `external_fetch_cache.kind` ไม่มี CHECK
   อยู่แล้ว จึงไม่ต้องแก้ (cache เป็น disposable; โค้ดใหม่ไม่มีทางเขียน kind `rss` อีก)
3. **API** — `RunBody` (`api/models.py`) และ `RunReadinessBody` (`api/routers/runs.py`) เพิ่ม
   validator `validate_source_kinds`: source ที่ kind ไม่ใช่ text/url = **422** ทั้ง `/runs`,
   `/runs/async` และ `/runs/readiness`. Rerun ของ legacy run ที่ request เดิมมี source `rss`:
   frozen rerun ตัด source นั้นออกได้อย่างปลอดภัย (หลักฐานอ่านจาก evidence snapshot ที่ freeze
   แล้ว ไม่ refetch) ส่วน latest rerun ที่ contract ไม่รองรับ = 422 พร้อมคำแนะนำใช้ frozen
4. **Frontend** — wizard NewRun เหลือปุ่ม kind 🔗 URL / 📄 วางข้อความ; `api.ts` `SourceInput.kind`
   เหลือ `"text" | "url"`; i18n ตัดคำว่า RSS จาก `wiz_src_desc`/`wiz_src_pii_note`/
   `wiz_src_need_value`. **Legacy read คงไว้**: ป้าย "📡 RSS" ใน Run Detail สำหรับแถว news/source
   ประวัติยังแสดงตามเดิม (mapping อ่านอย่างเดียว)
5. **Tests** — เพิ่ม: POST `/runs`//runs/async`//runs/readiness` ด้วย kind `rss` = 422;
   `ingest_sources` ปฏิเสธ `rss` โดยไม่ fetch; แถว legacy `kind='rss'` insert ผ่าน CHECK เดิม
   และอ่านผ่าน `retrieve_evidence` ได้
6. **`core/safe_fetch.py`** — ตัด `application/rss+xml`/`application/atom+xml` ออกจาก
   `DEFAULT_CONTENT_TYPES` (ไม่มี consumer ที่ parse feed อีกแล้ว — fetcher นี้ใช้เฉพาะ
   evidence `url`); `application/xml`/`text/xml` ทั่วไปยังรับเพราะเป็นเอกสาร XML ปกติ
7. **Bonus** — `simulation/newsdesk.py` ตั้ง `TAVILY_MAX_RESULTS = 3` เป็นค่าคงที่มีชื่อ
   (เจตนาไม่เป็น setting — caps ต่อ run เป็นด่านคุมปริมาณจริงอยู่แล้ว)

## สิ่งที่ *ไม่* เปลี่ยน

- ไม่มี migration — ไม่มีข้อมูลถูกลบ/แก้; แถวประวัติ `kind='rss'` ใน `run_sources` และ
  `external_fetch_cache` อ่านได้ต่อครบ (ต่างจาก ADR-0026 ที่มี operational cache ให้ล้าง)
- PII gate, SSRF guard (`validate_external_url` + `SafeOutboundFetcher`), BM25 retrieval,
  dedupe/quality provenance — ทำงานเหมือนเดิมกับ kind text/url

## ผลกระทบ

- supersede ส่วน "สิ่งที่ไม่ถูกถอด" ข้อ evidence sources ของ ADR-0026 — ตอนนี้ RSS ถูกถอด
  ครบทั้ง News Desk และ evidence sources; ผู้ใช้ที่เคยแนบฟีด RSS ใช้ kind `url` ชี้หน้าเว็บข่าวแทน
- ไม่มีผลต่อ governance ledgers: run/prediction/finding/audit append-only ไม่ถูกแตะ
