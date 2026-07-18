# ADR-0025 — ถอดกล่อง Simulation finding (UI) + ฟีเจอร์ Run repair และแก้บั๊ก Trust Scorecard

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งลบกล่อง "ข้อค้นพบจากการจำลอง" ใน Run Detail (เฉพาะชั้นแสดงผล), ลบฟีเจอร์
"ซ่อมแซมข้อมูลการรัน (Run repair)" ทั้งเส้นทาง และให้ review/แก้/แปล Trust Scorecard

## บริบท

ตามแนวทาง clean production เดียวกับ ADR-0019/0023/0024 — workflow หลักคือ
PopulationSet → Run → Result → Export. กล่อง finding/prediction contract ใน Run Detail
เป็น surface สร้างคำทำนาย manual ที่ไม่ได้ใช้งานจริง ส่วน Run repair
(refresh-news / resynthesize) เป็น legacy จากยุคที่ engine มี mechanical fallback —
ปัจจุบัน production Debate ใช้ analyst synthesis จริงแบบ fail-closed (ADR-0018)
เส้นทาง rebuild snapshot เชิงกลไกจึงขัดกับ contract "ไม่มี mechanical fallback"

## มติ

1. **ลบกล่อง Simulation finding / Prediction contract — UI เท่านั้น**
   - `web/src/pages/RunDetail.tsx`: ลบ section แสดง result_kind/claim/finding summary,
     ฟอร์มสร้าง prediction (`predictionOpen`/`predictionDraft`/`savePrediction`)
   - `web/src/api.ts`: ลบ `createPrediction` (มีผู้ใช้เดียวคือกล่องนี้); type
     `PredictionContract`/`SimulationFinding` คงไว้ (อยู่ใน `SimRunDetail` ที่ backend ยังส่ง)
   - i18n keys ที่ลบ (ใช้เฉพาะกล่องนี้): `rd_prediction_contract`, `rd_simulation_finding`,
     `rd_no_contract`, `rd_not_in_calibration`, `rd_create_prediction`, `rd_claim_ph`,
     `rd_measurement_ph`, `rd_probability`, `rd_save_append_only`
     (คง `rd_due_word`/`rd_validate_seeds`/`rd_prediction_note` ที่มีผู้ใช้อื่น)
   - **backend registry ไม่ถูกแตะทั้งหมด** (กฎเหล็กข้อ 3 / TRUST-01): ตาราง
     `simulation_findings`/`prediction_registry`, `register_finding`, `_register_run_result`,
     `finalize_run`, endpoint `POST /runs/{id}/predictions` และ `result_kind` ใน
     `/runs/{id}.json` ยังอยู่ครบ append-only — งานนี้ลบเฉพาะชั้นแสดงผล

2. **ลบ Run repair ทั้งฟีเจอร์**
   - Backend: endpoints `POST /runs/{run_id}/refresh-news` และ
     `POST /runs/{run_id}/resynthesize` (+alias `/recompute-metrics`) ใน `api/app.py`
     พร้อม helper `_news_payload_items`; `synthesize_snapshot` + `_mechanical_synthesis`
     ใน `simulation/debate.py` (ผู้เรียกเดียวคือ endpoint นี้ — production ใช้ analyst จริง
     fail-closed อยู่แล้ว); `RunStore.update_payload` ใน `core/runstore.py`
     (ผู้เรียกเดียวคือ refresh-news)
   - Frontend: กล่อง repair controls + `repair()`/`repairBusy` ใน RunDetail,
     `refreshRunNews`/`resynthesizeRun` ใน `api.ts`, i18n keys `rd_repair_title`,
     `rd_repair_desc`, `rd_refresh_news`, `rd_recompute`
   - Tests: ลบ `test_resynthesize_run_rebuilds_payload_from_posts` และ
     `test_refresh_news_updates_debate_payload` ใน `tests/test_jobs.py`
   - ไม่มีตาราง DB เฉพาะของ repair — ไม่ต้องมี migration (ยืนยันด้วย grep);
     `synthesis_revisions` คงไว้ (ผู้ใช้อื่นคือ analyst synthesis ใน run pipeline)

3. **Trust Scorecard (`core/run_quality.py::build_trust_scorecard`) — บั๊กที่พบและแก้**
   - **บั๊ก budget check**: `payload.get("cost_usd", 0) is not None` — เมื่อ key หายไป
     ได้ default 0 → `is not None` = True = pass เสมอ ทั้งที่เจตนาคือ warn เมื่อไม่มีข้อมูล
     ต้นทุน → แก้เป็น `payload.get("cost_usd") is not None`
   - **ไม่ engine-aware**: fabric (กลไก $0 ไม่มี LLM/posts/news/verifier/judge) โดน warn
     จากเช็ค debate 6 ตัว (sources/news/parse_failures/budget/deterministic_verifier/
     analyst_judge) ทำให้คะแนนต่ำอย่างหลอกๆ → เช็คเหล่านี้ append เฉพาะ engine ที่
     `uses_llm` (ตัดสินจาก `detail["engine"]` ผ่าน engine registry; engine ไม่รู้จัก =
     คงชุดเต็มแบบ conservative) จึงไม่เข้าตัวหารคะแนน; debate คงพฤติกรรมเดิมทุกเช็ค
   - **สูตรคะแนน**: earned = pass×w + 0.5×warn×w หาร total_weight ×100 — ตรวจแล้ว
     total_weight มาจาก checks ที่ append จริงหลังแก้ engine-aware; band เดิม
     (≥85 strong, ≥65 usable) คงไว้; unit tests ใหม่ `tests/test_trust_scorecard.py`
   - **แปลไทยที่ frontend**: RunDetail map check id → i18n key `rd_tsc_*` และ band →
     `rd_tsc_band_*` (fallback เป็น label/band ดิบจาก API เมื่อ id ไม่รู้จัก);
     detail string คงเป็น technical ตามเดิม

## ผลกระทบ

- ทุก run ยังสร้าง SimulationFinding/Prediction record อัตโนมัติผ่าน `finalize_run`
  ตามกฎเหล็กข้อ 3 — เปลี่ยนเฉพาะว่าผู้ใช้ไม่เห็นกล่องนี้และไม่สร้าง prediction จากหน้า
  Run Detail; การ resolve prediction เดิมทำผ่าน `scripts/resolve_predictions.py` ตามเดิม
- fabric run ที่ complete + manifest ครบ ได้ Trust Scorecard เต็มตามเช็คที่เกี่ยวจริง
  (ก่อนแก้: โดน warn/block จากเช็ค debate จน band ตกเป็น needs_review ทั้งที่ reproduce
  ได้ 100%)
- OpenAPI/generated TypeScript client เปลี่ยนตาม endpoint ที่หายไป
  (regenerate ด้วย `npm run generate:api`)
