# ADR-0008 — News Desk กลาง + Media Diet (SIM-11 เต็มรูป)

- วันที่: 12 ก.ค. 2569 | สถานะ: ใช้งาน (ผู้ใช้ approve แนวทาง + "เริ่มเลย ทำครบ M1-M4", เลือก RSS + Search API)
- บริบท: ผู้ใช้ต้องการให้ agent (persona) ดึงข้อมูลล่าสุดจากอินเทอร์เน็ตเองระหว่าง debate
  ("global knowledge") — ผลวิจัย: ยังไม่มี social simulation ไหนทำ (OASIS/GenSim/AgentSociety
  inject โดยผู้วิจัย) แต่ agentic search เดี่ยวๆ มีแพร่หลาย → ส่วน novel จริงคือ
  **persona-conditioned retrieval (media diet)**

## การตัดสินใจ

1. **โต๊ะข่าวกลาง ไม่ใช่ per-agent fetch** (`simulation/newsdesk.py`) — agent "แสดงเจตนาค้น"
   (field `want_to_know` ใน JSON) → โต๊ะข่าวรวบ dedupe (`dedupe_intents`, cap 3/รอบ) แล้วค้นให้
   เหตุผล: คุมงบ (n agents ค้นเอง = ระเบิด), คุม governance จุดเดียว, dedupe ได้
2. **Media diet**: `segment_feed()` ให้แต่ละ segment เห็นข่าว top-k ถ่วงด้วย channel_mix ของกลุ่ม
   × relevance (3-gram) × ความสด — deterministic ต่อ seed; **channel tags ของข่าวเป็น heuristic
   จาก provider** (RSS→public_feed หนัก, search→algo_feed หนัก) บันทึกตรงๆ ว่าไม่ใช่ข้อมูลการแพร่จริง
3. **Snapshot-first (NFR-07)**: ทุกชิ้น freeze ลง `news_items` ก่อนใช้ — replay/แสดงผลอ่านจาก
   `load_items()` เท่านั้น (มี test mock httpx ระเบิดถ้าแตะเน็ต)
4. **Governance เดิมครอบเต็ม**: `gather()` เรียก `ensure_external_retrieval_allowed()` ก่อน I/O
   (hindcast = ตาย — กฎเหล็กข้อ 2 + leak test). PII policy เดิมถูก ADR-0010 แทนที่เมื่อ
   15 ก.ค. 2569: body/title redact+ตรวจซ้ำก่อน persist; URL PII, detector ปิด หรือ verify ไม่ผ่าน = block
5. **Search = Tavily** (key `.env` `TAVILY_API_KEY`) — ไม่มี key = โหมด RSS อย่างเดียว (degrade ไม่พัง);
   caps: ≤30 items/run, ≤8 queries/run, intent ≤3/รอบ

## ทางเลือกที่ไม่เอา

- Per-agent autonomous tool calling — แพง (n× search + token), ช้า, audit ยาก, PII gate กระจาย
- Knowledge graph จากข่าวสด (แบบ SwarmSight graph_swarm) — ยังไม่มี embedding model ใน stack;
  lexical 3-gram พอสำหรับ k เล็ก (ทางอัปเกรดเดียวกับ sources.py)

## ผลกระทบ

- debate รับ `segment_news` + `news_fetcher`; DebatePost มี `want_to_know`; POST /runs รับ `live_news`
- payload.news เก็บรายการข่าว (ที่มา+เวลา+สถานะ PII) → tab เส้นทางหลักฐาน
- Hindcast Mode ใช้ live_news ไม่ได้โดยสถาปัตยกรรม (gate ที่ gather)
