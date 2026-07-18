# ADR-0024 — ถอดฟีเจอร์รายการติดตาม (Watchlist) ทั้งระบบ

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งลบ Watchlist ออกทั้งหมด — UI, API, backend, ตารางฐานข้อมูล และ tests

## บริบท

Watchlist (P5-M5) เป็น retention loop: subscribe หัวข้อ → Celery beat รันซ้ำตาม cadence
(daily/weekly) → alert `tipping_point`/`consensus_shift` + webhook Slack/Discord และ
unread badge บน sidebar. ผู้ใช้ตัดสินใจถอดฟีเจอร์นี้เพื่อ clean production ตามแนวเดียวกับ
ADR-0019/ADR-0023 — workflow หลักปัจจุบันคือ PopulationSet → Run → Result → Export
และไม่มีการใช้งาน Watchlist จริง (ทุกแถวใน DB เป็นข้อมูลที่ test suite สร้างทิ้งไว้)

## มติ

1. **Frontend** — ลบหน้า `web/src/pages/Watchlist.tsx`, route `/watchlist`, เมนู nav + icon
   Bell + unread badge ใน `App.tsx`, ลบ `web/src/api-shell.ts` ทั้งไฟล์ (มีไว้เพื่อ
   `fetchShellUnread` ของ watchlist อย่างเดียว — ตรวจแล้วไม่มีผู้ใช้อื่น), watchlist
   functions/types ใน `api.ts`, i18n keys `nav_watchlist`/`wl_*`/`tip_shift`/
   `set_webhook_on|off`, proxy `/watchlists` + `/alerts` ใน `vite.config.ts`
   และ stub `/watchlists.json` ในทุก Playwright spec
2. **Backend** — ลบ `api/routers/watchlists.py` (endpoints `/watchlists.json`, `/watchlists`,
   `/watchlists/{id}` delete/toggle/run, `/alerts/read`), `governance/watchlist.py`
   (WatchlistStore/check_watchlist/default_runner), Celery task `chimlang.check_watchlists`
   + beat entry `check-watchlists-hourly` ใน `core/tasks.py` และ targets watchlists/alerts
   ใน `scripts/cleanup_dev_data.py`; MCP surface ไม่มี watchlist tool อยู่แล้ว
3. **Webhook + config ลบทั้งเส้นทาง** — `governance/webhook.py` (`fire_webhook`) มี caller
   เดียวคือ watchlist จึงลบไฟล์; ลบ `alert_webhook_url` และ `consensus_shift_threshold`
   จาก `core/config.py` และ field `webhook_configured` จาก `/settings.json` + Settings UI
   (ข้อความ i18n ที่เคยอ้าง webhook URL ปรับเป็น bootstrap secrets ทั่วไป)
4. **Database** — migration `2026-07-18-remove-watchlists-v1` DROP ตาราง `alerts` และ
   `watchlists`; ตัด watchlist schema ออกจาก bootstrap `_apply_module_schemas`
   (DB ใหม่ไม่สร้างตารางนี้อีก และ DROP IF EXISTS เป็น no-op)
   **ตรวจก่อนลบ (18 ก.ค. 2026): `watchlists` 360 แถว, `alerts` 180 แถว — ทั้ง 360 แถว
   เข้าเงื่อนไข test marker ('ทดสอบ'/'shift'/'tip'/'api-test'/'x') = 0 รายการผู้ใช้จริง
   และ alerts ทั้งหมดเป็นลูกของแถว test เหล่านั้น (ON DELETE CASCADE)**
5. **Tests** — ลบ `tests/test_watchlist.py` ทั้งไฟล์ และตัด assertion `/watchlists` ออกจาก
   `test_api_rejects_too_few_agents_before_db` ใน `tests/test_phase6.py` (ส่วน `/runs`
   และ `/gallery/share` คงเดิม)

## ผลกระทบ

- supersede ส่วน Watchlist/alerts/webhook ของ Phase 5 M5 (PHASE5-BRIEF เป็นบันทึกประวัติ)
- append-only governance records ไม่ถูกแตะ: `audit_log` (รวม event `watchlist_check` เดิม),
  `prediction_registry`, `prediction_resolution`, `simulation_findings`, `run_manifests`
  และ financial ledgers คงอยู่ครบตาม GOV-04/TRUST-01
- REH-05 Divergence Alarm ใน war room (แผน Phase 10) เป็นคนละกลไก ไม่ได้ถูกถอดโดย ADR นี้
- ตัวแปร env `ALERT_WEBHOOK_URL`/`CONSENSUS_SHIFT_THRESHOLD` ที่ผู้ใช้อาจตั้งไว้ใน `.env`
  จะถูกเพิกเฉย (pydantic settings ไม่ strict) — ไม่มีผลข้างเคียง
