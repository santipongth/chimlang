# ADR-0026 — ถอด RSS ออกจากโต๊ะข่าวสด (Live News Desk) ให้เหลือ Tavily search อย่างเดียว

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งถอด RSS ออกจากโต๊ะข่าวสดทั้งหมด — ช่องตั้งค่าฟีด RSS ในหน้า Settings,
ค่า default, โค้ด, ไฟล์ และฐานข้อมูล — โต๊ะข่าวเหลือ Tavily search อย่างเดียว

## บริบท

โต๊ะข่าวสด (P7/SIM-11, ADR-0008) เคยมี 2 provider: RSS feeds (ข่าวแวดล้อม จัดอันดับ BM25
กับหัวข้อ run + กรองอายุข่าว `news_max_age_days`) และ Tavily search (ตรงหัวข้อ อยู่แล้ว).
ผู้ใช้ตัดสินใจถอด RSS เพื่อ clean production ตามแนว ADR-0019/0023/0024/0025 —
Tavily จัดอันดับตามคำค้นให้อยู่แล้ว จึงไม่ต้องมีชั้นจัดอันดับ/กรองอายุของฝั่ง RSS อีก

## มติ

1. **`simulation/newsdesk.py`** — ลบ `_parse_rss_entries`/`_parse_pub_date`/`_fetch_rss_items`,
   พารามิเตอร์ `feeds` ของ `gather()` และสาขา RSS ทั้งหมด (age filter + BM25 ranking ของ
   rss_candidates), `CHANNEL_TAGS["rss"]`, `NEWS_MAX_AGE_DAYS`, field `published_at` ใน
   `NewsItem` และจุดเขียน/อ่านทั้งหมด. `effective_news_config()` เหลือคืน Tavily key,
   `effective_news_tuning()` เหลือคืน cache TTL.
   **คงไว้**: near-duplicate dedupe (ใช้กับผลค้น), cache TTL (`news_cache_ttl_hours`),
   PII gate fail-closed, snapshot-first (NFR-07), hindcast gate (กฎเหล็กข้อ 2) และ
   failure/skipped evidence ("Tavily skipped: TAVILY_API_KEY ยังไม่ได้ตั้งค่า" ฯลฯ)
2. **Config/Settings** — ลบ `news_rss_feeds`/`news_rss_feeds_list()`/`news_max_age_days`
   จาก `core/config.py`; ลบ keys `news_rss_feeds`/`news_max_age_days` + validation จาก
   `core/appsettings.py` (PUT ด้วย key เหล่านี้ = 422 unknown key);
   `GET /settings.json` ตัด `feeds`/`feeds_source`/`max_age_days` ออกจาก `news` object;
   ลบ `NEWS_RSS_FEEDS` จาก `.env.example` (ค่าเก่าใน `.env` ถูกเพิกเฉย — pydantic ไม่ strict)
3. **API payload** — ตัด `published_at` ออกจาก news items ใน run payload (`api/app.py`);
   readiness message เปลี่ยนจาก `rss_or_tavily_will_be_checked_at_run_time` เป็น
   `tavily_will_be_checked_at_run_time` (`core/run_quality.py`)
4. **Database** — migration `2026-07-18-remove-news-rss-v1`:
   DROP COLUMN `news_items.published_at` (**ตรวจก่อนลบ 18 ก.ค. 2026: 91 แถวที่
   `published_at <> ''` ใน 13 run — 10 run เป็น `news-age-*` จาก test suite และ 3 run
   เป็น debate ของวันเดียวกันที่ column เพิ่งถูกเพิ่ม; ไม่มีข้อมูล production ก่อนหน้า**),
   ลบ `news_fetch_cache` แถว `provider='rss'` (190 แถว — operational cache ที่โค้ดใหม่
   ไม่มีทางอ้างถึงเพราะ cache key ผูก provider; cache เป็น disposable โดยนิยาม) และถอด
   keys RSS ที่เลิกใช้ออกจาก `app_settings.data` JSONB.
   **ห้ามแก้ CHECK constraint provider (`'rss','search'`)** — แถวเก่า `provider='rss'`
   ใน `news_items` (1,087 แถว ณ วันลบ) เป็น snapshot ประวัติที่ต้องอ่านได้ต่อ (NFR-07);
   `load_items()` คืน `channel_tags` ที่ snapshot ไว้กับแถว จึงไม่พึ่ง `CHANNEL_TAGS` ใน code
5. **Frontend** — Settings ลบ textarea ฟีด RSS และช่อง "อายุข่าวสูงสุด (วัน)"
   (คงช่อง cache TTL + Tavily key); `api.ts` ตัด types `news_rss_feeds`/`news_max_age_days`/
   `feeds`/`feeds_source`/`max_age_days`; i18n ลบ `set_news_feeds*`/`set_news_max_age*`/
   `set_news_days_unit`/`set_key_db_short`/`set_key_env_short` (สองตัวหลังไม่มีผู้ใช้อื่น)
   และปรับ `set_news_desc`/`set_tavily_none`/`wiz_news_desc` ให้พูดถึง Tavily อย่างเดียว;
   ปรับ stub settings ใน `web/e2e/accessibility.spec.ts`
6. **Tests** — `tests/test_newsdesk.py` ย้าย scenario cache reuse / near-dup / PII redaction
   ไป monkeypatch `_tavily_search` + stub `effective_news_config` ด้วย key ปลอม
   (ห้ามยิง Tavily จริงตาม ADR-0021); ลบ tests ของ pub date/age filter/BM25 rss ranking;
   เพิ่ม test อ่านแถว legacy `provider='rss'` ผ่าน `load_items` + `segment_feed` และ test ว่า
   PUT keys RSS เดิมถูกปฏิเสธ

## สิ่งที่ *ไม่* ถูกถอด (คนละฟีเจอร์)

- **Evidence sources ต่อ run** (`simulation/sources.py`, kind `rss` ในกล่องแหล่งข้อมูลของ
  wizard/NewRun) — ผู้ใช้สั่งเฉพาะโต๊ะข่าวสด; การแนบ RSS link เป็นหลักฐานประกอบ debate
  ยังทำงานตามเดิมผ่าน PII gate เดียวกัน
- แถว snapshot เก่า `provider='rss'` ใน `news_items` และการแสดงผลใน Run Detail
  (ป้าย "📡 RSS" สำหรับแถว legacy) — ประวัติต้องอ่านได้ต่อ

## ผลกระทบ

- supersede ส่วน RSS ของ ADR-0008 (News Desk + media diet) และ migration
  `2026-07-18-news-published-at-v1` (column ที่เพิ่มเช้าวันเดียวกันถูก drop โดย migration นี้);
  media diet ราย segment ยังทำงานเหมือนเดิมกับผลค้น Tavily
- ไม่มี key Tavily = โต๊ะข่าวไม่มีข่าวเข้า run (snapshot `skipped` เป็นหลักฐาน) —
  เดิม RSS เป็น fallback; ผู้ใช้ที่เปิดโหมดข่าวสดต้องตั้ง `TAVILY_API_KEY` (.env หรือหน้า Settings)
- governance ครบเดิมทุกด่าน: hindcast gate ก่อน I/O, PII redact→re-scan fail-closed,
  snapshot-first replay ไม่แตะเน็ต, audit/append-only records ไม่ถูกแตะ
