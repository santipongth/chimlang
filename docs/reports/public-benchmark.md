<!-- chimlang-watermark:{"run_id": "benchmark-page-20260712-165355", "exported_at": "2026-07-12T09:53:55+00:00", "label": "AI simulation — not a real poll"} -->
> ⚠️ **AI simulation — not a real poll** — ผลจำลองโดย AI (ชิมลาง) ไม่ใช่โพลจริง | run: `benchmark-page-20260712-165355` | export: 2026-07-12T09:53:55+00:00

# ชิมลาง — Public Benchmark (ผลทั้งหมด ทั้งผ่านและไม่ผ่าน)

> ⚠️ ทุกตัวเลขในหน้านี้เป็น simulation_estimate ระดับ aggregate — not_field_poll (GOV-02)

## Hindcast benchmark (TRUST-03)

- รันเมื่อ: 2026-07-12 15:41 | agents/target: 5 (ภายใต้ cap พัฒนา ≤ 1000) | ต้นทุน: $0.1675
- ผล: **ผ่าน 9/10 เหตุการณ์** (เกณฑ์เฟส: ≥ 3)

| เหตุการณ์ | target | ทำนาย | ผลจริง | ถูก? |
|---|---|---|---|---|
| 2565-bkk-governor-election | winner_landslide | True | True | ✅ |
| 2565-bkk-governor-election | turnout_above_60 | True | True | ✅ |
| 2565-true-dtac-merger | merger_proceeds | True | True | ✅ |
| 2565-true-dtac-merger | conditions_attached | True | True | ✅ |
| 2565-world-cup-broadcast | free_broadcast_secured | True | True | ✅ |
| 2565-world-cup-broadcast | platform_dispute | True | True | ✅ |
| 2566-general-election | mfp_most_seats | True | True | ✅ |
| 2566-general-election | turnout_above_70 | True | True | ✅ |
| 2566-pm-vote | leader_becomes_pm | False | False | ✅ |
| 2566-pm-vote | next_pm_from_second_party | True | True | ✅ |
| 2567-digital-wallet-phase1 | phase1_cash_september | True | True | ✅ |
| 2567-digital-wallet-phase1 | phase1_over_10m | True | True | ✅ |
| 2567-marriage-equality | senate_approves | True | True | ✅ |
| 2567-marriage-equality | effective_by_jan2025 | True | True | ✅ |
| 2567-mfp-dissolution | party_dissolved | True | True | ✅ |
| 2567-mfp-dissolution | mps_regroup_fast | True | True | ✅ |
| 2567-mpc-rate-decision | rate_cut_under_pressure | False | False | ✅ |
| 2567-mpc-rate-decision | split_vote | True | True | ✅ |
| 2567-pm-srettha-ruling | pm_removed | False | True | ❌ |
| 2567-pm-srettha-ruling | new_pm_same_month | True | True | ✅ |

## Calibration Dashboard (TRUST-02)

- ณ วันที่: 2026-07-12 | Brier score: 0 = สมบูรณ์แบบ, 0.25 = เดามั่ว (baseline)

| โดเมน | resolved | mean Brier | baseline | ดีกว่า baseline? |
|---|---|---|---|---|
| ทดสอบ-calibration | 240 | 0.337 | 0.25 | ❌ |
| ทดสอบ-p5m3 | 100 | 0.120 | 0.25 | ✅ |

## ข้อจำกัดที่ต้องรู้ (เผยแพร่คู่ผลลัพธ์เสมอ)

1. เหตุการณ์ hindcast อยู่ใน training data ของ LLM — leak test คุมการเผยผลชัดแจ้ง (รายละเอียดใน docs/reports/) แต่ prior contamination ตัดไม่ได้ 100% → ผล hindcast เป็นเงื่อนไขจำเป็น ไม่ใช่ข้อพิสูจน์สุดท้าย
2. รันภายใต้ข้อจำกัดช่วงพัฒนา (≤ 10 agents) — ผลที่ scale จริงต้องวัดซ้ำ
3. Calibration ที่แท้จริงมาจากคำทำนายเหตุการณ์อนาคตที่ resolve ตามกำหนดเท่านั้น
4. ผลต่างกันได้เล็กน้อยระหว่างรอบรัน (LLM non-determinism แม้ pin seed) — target ที่เสียงโหวตก้ำกึ่งอาจพลิกข้ามรอบ (สังเกตจริง: 4/5 → 5/5 ในสองรอบติดกัน); รายงานทุกรอบถูกเก็บถาวร ไม่เลือกเฉพาะรอบที่สวยที่สุด

---
> ⚠️ AI simulation — not a real poll | run `benchmark-page-20260712-165355`
