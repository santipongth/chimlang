# ADR-0017 — Worker readiness แบบ fail-closed

สถานะ: Accepted
วันที่: 17 ก.ค. 2026
ขอบเขต: asynchronous runs สำหรับ self-hosted single-tenant

## บริบท

Redis broker อาจพร้อมรับ task ขณะที่ไม่มี Celery worker ทำงาน. เดิม `/health/deep` ตรวจ Redis แต่ไม่ตรวจ
consumer และ `POST /runs/async` สร้างแถว `queued` ก่อนส่ง task จึงเกิดสถานะ `รอ worker` ที่ไม่มีผู้ประมวลผล
จริง. เหตุการณ์ 17 ก.ค. ทำให้ Debate run ของผู้ใช้ค้างจนเปิด worker ด้วยตนเอง.

## มติ

1. Celery worker เขียน heartbeat timestamp ลง Redis ทุก 5 วินาทีด้วย TTL 20 วินาที. ค่านี้เป็น ephemeral
   operational signal ไม่ใช่ provenance หรือผล simulation
2. `/health/deep` แสดง `worker` เป็น component แยกจาก `redis`; overall health เป็น degraded เมื่อ heartbeat
   หายหรือ Redis อ่านไม่ได้
3. non-eager async run ต้องพบ heartbeat สดก่อน persist queued row. หากไม่พบให้ตอบ 503 และไม่สร้าง run;
   request เดิมที่ตรงกับ Idempotency-Key ที่เคยรับแล้วคืนสถานะเดิมได้โดยไม่ต้องมี worker
4. worker command มาตรฐานต้อง subscribe `fabric,debate,maintenance` ให้ตรง task routes. readiness มี detection
   window สูงสุดตาม TTL และ live end-to-end smoke เป็นหลักฐานว่าคิวที่ subscribe ประมวลผลได้จริง

## ผลตามมา

- ผู้ใช้ไม่เห็น queued ใหม่แบบไม่มีกำหนดเมื่อ worker ไม่ได้เปิด แต่ได้รับ error ที่แก้ไขได้ทันที
- Redis พร้อมอย่างเดียวไม่สามารถทำให้ deep health เป็น ok ได้อีก
- heartbeat ไม่ใช่ distributed scheduler guarantee; การ deploy หลาย worker ในอนาคตควรเปลี่ยนเป็น per-worker/
  per-queue readiness และ aggregation โดย ADR ใหม่
- task ที่รับก่อน worker ล่มยังคงอยู่ใน Redis ตาม Celery delivery semantics และจะทำต่อเมื่อ worker กลับมา
