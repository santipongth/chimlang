"""ล้างข้อมูล dev/test ที่สะสมใน DB (P5 เก็บตก — 12 ก.ค. 2026)

    uv run python scripts/cleanup_dev_data.py          # ดูจำนวนที่จะถูกลบ (dry-run)
    uv run python scripts/cleanup_dev_data.py --yes    # ลบจริง

ขอบเขต: ลบเฉพาะ **ตาราง operational** (watchlists/alerts/gallery/persona_packs)
ที่ tests และการทดลอง dev สร้างทิ้งไว้ — ระบุด้วย marker คำว่า "ทดสอบ" หรือ
label/subject ที่ test suite ใช้

**ห้ามแตะ**: prediction_registry / prediction_resolution / audit_log — เป็น
append-only ด้วย PostgreSQL trigger (TRUST-01/GOV-04) ลบไม่ได้โดยออกแบบ
→ ขยะ test ในตารางเหล่านั้นถูก "กรองที่ชั้นอ่าน" แทน (UI ไม่แสดง domain 'ทดสอบ%')
"""

import argparse

import psycopg

from core.config import get_settings

# เงื่อนไขระบุแถวที่มาจาก test/dev — อิง marker ที่ test suite ใช้จริง
TARGETS: list[tuple[str, str]] = [
    (
        "watchlists",
        "label LIKE '%ทดสอบ%' OR subject LIKE '%ทดสอบ%' OR label IN ('shift', 'tip', 'api-test')",
    ),
    ("alerts", "watchlist_id IS NULL"),  # ที่เหลือถูกลบตาม cascade ของ watchlists
    ("gallery_shares", "subject LIKE '%ทดสอบ%' OR subject LIKE 'หัวข้อ%' OR created_by = 'test'"),
    ("persona_packs", "label LIKE '%ทดสอบ%' OR prompt LIKE '%ทดสอบ%' OR created_by = 'test'"),
    ("sim_runs", "subject LIKE '%ทดสอบ%'"),  # debate_posts ลบตาม cascade
    ("llm_spend", "run_id LIKE '%test%' OR run_id = '' OR run_id LIKE '%ทดสอบ%'"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="ลบจริง (ไม่ใส่ = dry-run)")
    args = parser.parse_args()

    settings = get_settings()
    with psycopg.connect(settings.postgres_url) as conn:
        total = 0
        for table, cond in TARGETS:
            try:
                n = conn.execute(f"SELECT count(*) FROM {table} WHERE {cond}").fetchone()[0]  # noqa: S608 — cond เป็นค่าคงที่ในไฟล์นี้ ไม่ใช่ input ผู้ใช้
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                print(f"  {table}: ยังไม่มีตาราง (ข้าม)")
                continue
            total += n
            print(f"  {table}: {n} แถวเข้าเงื่อนไข")
            if args.yes and n:
                conn.execute(f"DELETE FROM {table} WHERE {cond}")  # noqa: S608
        if args.yes:
            print(f"\nลบแล้ว {total} แถว ✅")
        else:
            print(f"\nรวม {total} แถว — ใส่ --yes เพื่อลบจริง")
        print(
            "\nหมายเหตุ: prediction_registry/resolution/audit_log เป็น append-only ลบไม่ได้ "
            "(TRUST-01/GOV-04) — UI กรอง domain 'ทดสอบ%' ออกให้แล้ว"
        )


if __name__ == "__main__":
    main()
