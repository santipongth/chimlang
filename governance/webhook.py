"""Webhook delivery (P5-M5) — แจ้งเตือน tipping/consensus shift ออกนอกระบบ

กติกา (บทเรียนจาก SwarmSight ที่เอามา + ที่เราเข้มกว่า):
- best-effort เสมอ: webhook พัง/ช้า/URL ผิด ห้ามทำให้ run หรือ alert ในระบบพัง
- https เท่านั้น (http = ปฏิเสธเงียบ) และ **ห้าม log URL** — เป็น secret จาก .env
- payload ส่งทั้ง `text` (Slack) และ `content` (Discord) ให้เข้ากันได้กว้างสุด
"""

import httpx

from core.config import get_settings


def fire_webhook(kind: str, payload: dict, *, url: str | None = None) -> bool:
    """POST alert ไป webhook — คืน True ถ้ายิงสำเร็จ, False ถ้าไม่ได้ยิง/พัง (ไม่ raise)"""
    target = url if url is not None else get_settings().alert_webhook_url
    target = (target or "").strip()
    if not target.startswith("https://"):
        return False  # ไม่มี/ไม่ปลอดภัย = ไม่ยิง (fail-closed แบบเงียบ — โดยเจตนา)
    title = {
        "tipping_point": "⚡ ชิมลาง: พบ tipping point",
        "consensus_shift": "📈 ชิมลาง: ผลจำลองเปลี่ยนทิศ (consensus shift)",
    }.get(kind, f"🔔 ชิมลาง: {kind}")
    subject = payload.get("subject", "")
    body = {
        "text": f"{title} — {subject}".strip(" —"),
        "content": f"{title} — {subject}".strip(" —"),
        "username": "chimlang",
        "kind": kind,
        "payload": payload,
    }
    try:
        httpx.post(target, json=body, timeout=5.0)
        return True
    except Exception:
        return False  # ห้าม log รายละเอียด (อาจมี URL/secret ปน)
