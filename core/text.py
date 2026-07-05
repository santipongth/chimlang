"""utilities ข้อความจาก LLM ที่ใช้ร่วมทุก module"""

import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def sanitize_llm_text(text: str) -> str:
    """ตัด artifact ของ model (think tag หลุด ฯลฯ) — ใช้กับทุกคำตอบ crowd model"""
    text = _THINK_RE.sub("", text)
    return text.replace("</think>", "").replace("<think>", "").strip()
