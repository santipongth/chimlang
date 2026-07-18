# ADR-0028 — Debate อ้างอิงหลักฐานจริง + โหมดน้ำเสียง (discourse register) + กรองข่าว Tavily

สถานะ: Accepted
วันที่: 19 ก.ค. 2026
มติ: ผู้ใช้พบ debate หัวข้อกีฬา ("สเปนเป็นแชมป์ฟุตบอลโลก 2026") แล้วตัวแทนพูดวนเรื่องปากท้อง
ไม่ถกจากหลักฐาน จึงสั่งแก้ 3 เรื่อง: กรองข่าวให้สะอาด + ให้ agent อ้างอิงหลักฐาน +
เพิ่มโหมดน้ำเสียงเลือกต่อ run (คนไทยจ๋า / ทางการ) พร้อม advisory เตือน persona ไม่เข้ากับโจทย์

## บริบท (วินิจฉัยจาก run จริง)

1. **Persona pack เริ่มต้นตายตัวสำหรับโจทย์นโยบาย/สังคม** — ทุก segment มี cultural priors
   เรื่องภาระครัวเรือน system prompt จึงกรอบให้ตัวแทนอ่านทุกโจทย์ผ่าน "กระเป๋าเงิน" —
   โจทย์กีฬา/ข้อเท็จจริงหลุดกรอบที่ pack ออกแบบไว้
2. **Prompt สั่งเขียน "โพสต์ตามเสียงกลุ่ม ≤60 คำ" ไม่บังคับ reason จากหลักฐาน/ไม่บังคับ cite** —
   1/120 โพสต์เท่านั้นที่ cite; crowd รัน reasoning=False ได้ vibe ไม่ใช่การถก
3. **ข่าว Tavily เป็นขยะ** — general search คืน cookie-consent banner, แทคติกเกม FIFA,
   สถิติพรีเมียร์ลีกที่ไม่เกี่ยว; `_strip_html` เก็บ nav cruft; ไม่มีตัวกรอง relevance/quality

## มติ

1. **กรองข่าว Tavily + จัดอันดับ (`simulation/newsdesk.py`)** — เพิ่ม `_is_low_quality(title, content)`
   ตัด boilerplate (วลี cookie/nav cruft + เนื้อหาสั้น < 80 ตัวอักษร) และ `_rank_search_items()`
   ให้คะแนน BM25 (`_bm25_scores` จาก `simulation/sources.py`) เทียบ `queries[0]` (หัวข้อ run)
   → เก็บเฉพาะคะแนน > 0 เรียงมากไปน้อย (off-topic เช่น เกม/พรีเมียร์ลีก คะแนน ~0 ถูกตัด)
   ก่อนเข้าเพดาน `MAX_ITEMS_PER_RUN`. รายการ blocked/error/skipped ไม่เข้าคิวจัดอันดับ —
   ผ่านตรงเพื่อคง snapshot เป็นหลักฐาน. **คงเดิม**: cache TTL, near-dup, PII gate fail-closed,
   snapshot-first (NFR-07), hindcast gate (กฎเหล็กข้อ 2). ไม่เพิ่ม RSS กลับ (ADR-0026)
2. **Debate อ้างอิงหลักฐาน (`simulation/debate.py`)** — ใส่ N-id (N1, N2, …) ให้ข่าวใน `news_block`
   คู่กับ E-id ของ evidence sources; task line บังคับ: ถ้าอ้างข้อเท็จจริงต้องอิงข่าว/เอกสารที่ให้
   และใส่ ID ใน `evidence_refs`, ไม่มีหลักฐาน = บอกว่ายังไม่มีข้อมูล ห้ามกุ (Honesty over impressiveness).
   verifier ยอมรับ N-id ของข่าวที่แสดงจริง (`evidence_ids ∪ news_ids_seen`) จึงไม่ flag citation ข่าว
   เป็น unknown_evidence. เพิ่ม metric `evidence_citation_rate` (สัดส่วนโพสต์ ok ที่ cite) ใน `_compute_metrics`
3. **โหมดน้ำเสียง (discourse register) per-run** — `discourse_register ∈ {citizen, analyst}`
   default `citizen`:
   - `RunBody` (`api/models.py`) + `RunReadinessBody` (`api/routers/runs.py`) เพิ่ม field
   - `api/app.py` เก็บใน run config + ส่งเข้า `run_debate`; `core/run_manifest.py` เพิ่มใน canonical
     config (reproducibility) แบบ additive
   - `run_debate(..., discourse_register)` → `_persona_system(p, register)` + ตัวสร้าง user prompt:
     - **citizen** = ข้อความ system/task เดิม (persona voice/เกรงใจ/มีม-ประชด/≤60 คำ) + grounding
     - **analyst** = reframe เป็นนักวิเคราะห์ ภาษาทางการ อ้างหลักฐานเป็นหลัก ไม่ใช้มีม/ประชด
       ไม่โยงปากท้องถ้าไม่เกี่ยวโจทย์; task ยาวได้เล็กน้อย (≤90 คำ) + บังคับ grounding
     - Red Team role (contrarian/auditor/redteam) layer ทับได้ทั้งสองโหมด (คง cap จุดยืน/ห้าม concede
       ของ contrarian)
   - Frontend (`web/src/pages/NewRun.tsx`): การ์ดเลือก 2 ใบ (🗣️ คนไทยจ๋า / 📊 ทางการ) แสดงเฉพาะ
     engine debate, default citizen; `web/src/api.ts` + i18n `wiz_register_*`; regenerate OpenAPI
4. **Persona-fit advisory (`core/run_quality.py` `build_readiness`, debate เท่านั้น)** — check
   `persona_fit`: register=citizen → `warn` (persona pack เริ่มต้นออกแบบเพื่อโจทย์นโยบาย/สังคมไทย
   โจทย์ข้อเท็จจริง/ต่างประเทศ/กีฬาแนะนำโหมดทางการ); register=analyst → `pass`. **warn เฉยๆ ไม่ block**
   — เป็น advisory ที่ซื่อสัตย์ ไม่ใช่ classifier เดาโดเมนที่พลาดได้

## ทางเลือกที่พิจารณาแล้วไม่เอา

- **Auto-classify โดเมนโจทย์แล้วสลับ persona อัตโนมัติ** — classifier เดาผิดได้และซ่อนสมมติฐาน
  จากผู้ใช้; เลือก advisory + ผู้ใช้ตัดสินใจแทน (โปร่งใสกว่า)
- **ตัดเรื่องปากท้องออกจาก persona pack** — จะ regress โจทย์นโยบาย/สังคมที่ pack ออกแบบมาดี;
  เลือกทำเป็นโหมดสลับต่อ run แทน

## ผลกระทบ / governance

- ไม่มี migration — `discourse_register` อยู่ใน run config JSON, `evidence_citation_rate` ใน payload
  (additive ทั้งคู่); manifest config_hash ของ run ใหม่รวม field นี้ (reproducibility)
- ตามนโยบาย pilot (ADR-0021) validate ด้วย FakeAdapter/stub — ไม่เรียก LLM/Tavily จริงใน test;
  ผู้ใช้ทดสอบ live เอง (รันหัวข้อสเปนซ้ำทั้งสองโหมดแล้วเทียบ)
- governance ครบเดิม: hindcast gate ก่อน I/O, PII redact→re-scan fail-closed, snapshot-first replay,
  append-only registry ไม่ถูกแตะ; news filter เป็น pure ranking ไม่ข้าม PII/snapshot ด่านใด
