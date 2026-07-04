# population — สัดส่วน segment สำหรับ persona factory (M3)

ไฟล์ `segments.yaml`: ชื่อกลุ่ม, สัดส่วน, ช่องทางสื่อหลัก, ลักษณะเด่น

## ⚠️ สถานะ

`segments.yaml` เป็น **ร่างสังเคราะห์** (โดย Claude, 5 ก.ค. 2026) — สัดส่วนและ channel mix เป็นค่าประมาณเพื่อการพัฒนา ไม่ได้อ้างอิงสำมะโนจริง ก่อนใช้ผลิตผลลัพธ์จริงต้องปรับน้ำหนักตามข้อมูล สสช. / สำรวจการใช้สื่อ ตาม PRD หัวข้อ 9 (Data Requirements)

โครงสร้างที่ persona factory จะอ่าน: `share`, `channel_mix` (4 ช่องทางตาม FAB-01), `cultural_priors` (เกรงใจ / say-do gap / ประชด — FAB-02), `voice_activity` (ผู้แสดงออก vs ผู้สังเกตการณ์ — รากฐาน TRUST-07)
