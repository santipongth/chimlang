<!-- chimlang-watermark:{"run_id": "scale-20260706-023022", "exported_at": "2026-07-05T19:36:39+00:00", "label": "AI simulation — not a real poll"} -->
> ⚠️ **AI simulation — not a real poll** — ผลจำลองโดย AI (ชิมลาง) ไม่ใช่โพลจริง | run: `scale-20260706-023022` | export: 2026-07-05T19:36:39+00:00

# Scale Measurement (P3-S) — หลังยกเลิก cap 10 agents

- วันที่: 2026-07-06 02:30 | cap ใหม่: 1000 agents/run

## 1) เวลา multiverse what-if (5 universes × 4 seeds × 2 branches, กลไกล้วน $0)

| agents | rounds | เวลา (วิ) | fragility | delta ฐาน |
|---|---|---|---|---|
| 100 | 30 | 0.3 | 0/100 | +0.8% |
| 1000 | 30 | 5.8 | 20/100 | -1.2% |

## 2) ต้นทุน voice ต่อ call (วัดจริง 10 calls/โหมด)

- thinking on (คุณภาพเต็ม ADR-0001): $0.001115/call
- thinking off (โหมดเร็ว interactive): $0.000037/call

## 3) ประมาณการ Standard run เต็มรูป (1,000×30×5u, voice-sparse 15%)

- voice calls ที่ต้องใช้: 22,500
- แบบ thinking-on: **$25.09** → exit criteria Phase 0 (≤$80): ผ่าน ✅ | เป้า PRD (≤$50): ผ่าน ✅
- แบบ thinking-off: **$0.82** → exit criteria Phase 0 (≤$80): ผ่าน ✅ | เป้า PRD (≤$50): ผ่าน ✅

หมายเหตุซื่อสัตย์: ตัวเลขจาก extrapolation ของต้นทุน/call ที่วัดจริง — การรัน voice 22,500 calls จริงยังไม่ได้ทำ (จะกิน RUN_BUDGET_USD_CAP); เวลากลไกวัดเต็มจริงแล้วในตาราง 1

---
> ⚠️ AI simulation — not a real poll | run `scale-20260706-023022`
