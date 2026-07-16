# P8-M8 Production Soak Report

วันที่: 16 ก.ค. 2026

## วัตถุประสงค์

ตรวจเส้นทาง production-like นอก process ตั้งแต่ FastAPI รับ HTTP, สร้าง run ใน PostgreSQL, enqueue ผ่าน Redis,
Celery worker ประมวลผล, polling อ่าน terminal state และอ่าน run detail/event กลับมา โดยใช้ Fabric เพื่อไม่เรียก LLM
และไม่ใช้งบ provider

คำสั่ง:

```powershell
uv run python -m scripts.production_soak --runs 20 --concurrency 5 --agents 100 --timeout 180
```

Environment: Windows local self-hosted stack, FastAPI `127.0.0.1:8000`, PostgreSQL pgvector 16,
Redis 7, Celery solo worker queues `fabric,debate,maintenance`; schema migration รายงาน current ก่อนเริ่ม

## ผลดิบสรุป

| Metric | Result |
|---|---:|
| requested / passed / failed | 20 / 20 / 0 |
| concurrency / agents per run | 5 / 100 |
| p50 total latency | 1.657 s |
| p95 total latency | 2.214 s |
| heartbeat coverage | 100% |
| event coverage | 100% |
| events per completed run | 6 |
| missing/duplicate event IDs | 0 |
| timeout/stale/deadlock/run-id collision | 0 |

runner อ่าน detail สำเร็จก่อน cleanup ทุกงานและลบทั้ง 20 soak runs หลังเก็บผล จึงไม่ปนใน history/calibration.

## ขอบเขตที่พิสูจน์และข้อจำกัด

ผลนี้พิสูจน์ baseline concurrency ของ Fabric ผ่าน local production services และจับ queue/DB/event contract จริง
ไม่ใช่ mocked browser payload. ยังไม่ใช่หลักฐาน public-GA/load capacity: ไม่มี TLS/OIDC, ไม่มีการตัด network เพื่อ
พิสูจน์ SSE reconnect, ไม่ชน monthly budget reservation และไม่ใช้ paid Debate/1,000-agent payload. งานเหล่านี้
คงอยู่ใน `docs/FUTURE-WORK.md` และต้องใช้ isolated test environment/budget ก่อนรัน

## Acceptance

P8-M8 baseline ผ่าน: 20 concurrent run/read ไม่มี deadlock, ทุก completed job มี heartbeat หรือสถานะที่ตรวจสอบได้,
event IDs ไม่หาย/ซ้ำใน snapshot และ read-after-write สำเร็จทุกงาน
