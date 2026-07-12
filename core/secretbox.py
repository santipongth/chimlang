"""เข้ารหัส secret ก่อนเก็บใน DB (P6-M5, ADR-0007)

ผู้ใช้อนุญาตให้ตั้ง LLM API key จากหน้าเว็บ (แทน .env) โดยเก็บใน DB **แบบเข้ารหัส** —
กุญแจหลัก (master key) ยังอยู่ .env จุดเดียว (`CHIMLANG_SECRET_KEY`) ดังนั้นต่อให้
DB dump/backup รั่ว ก็ถอด key ไม่ได้ถ้าไม่มี master key

fail-closed: ไม่มี master key = เก็บ/อ่าน secret ที่เข้ารหัสไม่ได้ (ปฏิเสธ ไม่ fallback plain)
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings


class MasterKeyMissingError(RuntimeError):
    def __init__(self):
        super().__init__(
            "ยังไม่ได้ตั้ง CHIMLANG_SECRET_KEY ใน .env — ต้องมีกุญแจหลักก่อนจึงเก็บ API key ใน DB ได้ "
            '(สร้างด้วย: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())")'
        )


def _fernet() -> Fernet:
    raw = get_settings().secret_key.strip()
    if not raw:
        raise MasterKeyMissingError()
    # รับได้ทั้ง Fernet key มาตรฐาน (base64 44 ตัว) หรือ passphrase อิสระ (derive เป็น key)
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError):
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return Fernet(derived)


def encrypt(plaintext: str) -> str:
    """คืน ciphertext (str) — ปลอดภัยเก็บใน DB"""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """ถอดรหัส — master key ผิด/เปลี่ยน = InvalidToken (ห้ามคืน plaintext มั่ว)"""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError(
            "ถอดรหัส secret ไม่สำเร็จ — master key อาจถูกเปลี่ยน (CHIMLANG_SECRET_KEY)"
        ) from e


def mask(secret: str) -> str:
    """แสดงบางส่วนบนจอ — ไม่โชว์เต็ม (เช่น sk-or-...aB3z)"""
    s = secret.strip()
    if len(s) <= 8:
        return "•" * len(s)
    return f"{s[:6]}…{s[-4:]}"


def master_key_present() -> bool:
    return bool(get_settings().secret_key.strip())
