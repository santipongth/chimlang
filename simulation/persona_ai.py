"""AI-generate persona pack จาก prompt + single-persona simulator "ลอง ask" (P5-M7)

แนวคิดจาก SwarmSight (generatePersonasFromPrompt + simulatePersonaReply) แปลงเข้า
กติกาเรา:
- ทุก LLM call ผ่าน adapter เดียว + BudgetGuard (ประเมิน cost ก่อนเริ่มเสมอ)
- generate ใช้ analyst tier + temperature 0 + บังคับ JSON + retry 1 ครั้งเมื่อ parse พัง
  (pattern เดียวกับ LLM judge — parse พังซ้ำ = raise ไม่เดาต่อ)
- try-ask ใช้ crowd tier + reasoning=False (path interactive — บทเรียน 6 ก.ค.: เร็วขึ้น 29x)
- ผลลัพธ์ทุกชิ้นผ่าน validate_pack (รวม PII gate GOV-01) ก่อนถึงมือผู้ใช้
"""

import json
import re

from core.config import get_settings
from core.llm.adapter import LLMAdapter, ModelTier
from core.llm.cost import BudgetGuard, CostEstimator, TierLoad
from core.llm.pricing import PricingRegistry
from core.text import sanitize_llm_text
from simulation.persona_packs import (
    MAX_SEGMENTS,
    MIN_SEGMENTS,
    PRIOR_KEYS,
    VALID_CHANNELS,
    validate_pack,
)

_GEN_SYSTEM = f"""คุณคือผู้ช่วยออกแบบกลุ่มประชากรจำลอง (persona segments) สำหรับ social simulation ไทย
ตอบภาษาไทยเท่านั้น และตอบเป็น JSON ล้วนๆ (ไม่มี markdown ไม่มีคำอธิบาย)

กติกาเข้มงวด:
- ห้ามใช้ชื่อบุคคลจริงหรือข้อมูลส่วนบุคคลใดๆ — segment คือ "กลุ่มคน" ไม่ใช่บุคคล
- สร้าง {MIN_SEGMENTS}-{MAX_SEGMENTS} segments, share ทุกตัวรวมกัน = 1.0 พอดี
- channel_mix ใช้ได้เฉพาะ: {", ".join(VALID_CHANNELS)} และรวมกัน = 1.0 ต่อ segment
- cultural_priors ต้องมีครบ: {", ".join(PRIOR_KEYS)} (ค่า 0-1)

รูปแบบ JSON:
{{"segments": [{{"id": "slug_ascii", "name": "ชื่อกลุ่มภาษาไทย", "share": 0.3,
"voice_activity": 0.5,
"cultural_priors": {{"kreng_jai": 0.5, "say_do_gap": 0.4, "sarcasm_meme": 0.3}},
"channel_mix": {{"line_closed_group": 0.3, "public_feed": 0.3, "algo_feed": 0.25,
"offline_wom": 0.15}},
"traits": ["ลักษณะเด่น 2-3 ข้อ"]}}]}}"""


def _make_adapter() -> LLMAdapter:
    settings = get_settings()
    pricing = PricingRegistry.from_yaml()
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    # ประเมินก่อนเริ่มตามกติกา — งานนี้เล็ก (1-2 calls) แต่ด่านต้องผ่านเสมอ
    guard.check_estimate(
        CostEstimator(pricing).estimate([TierLoad(settings.llm_model_analyst, 2, 1500, 1500)])
    )
    return LLMAdapter(settings, pricing, guard)


def _parse_segments(text: str) -> list[dict]:
    clean = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(clean)
    segments = data["segments"] if isinstance(data, dict) else data
    if not isinstance(segments, list):
        raise ValueError("JSON ไม่ใช่ list ของ segments")
    return segments


def generate_pack_from_prompt(
    prompt: str, *, label: str, adapter: LLMAdapter | None = None
) -> list[dict]:
    """สร้าง segments จากคำอธิบาย audience — validate + PII gate ก่อนคืนเสมอ"""
    adapter = adapter or _make_adapter()
    messages = [
        {"role": "system", "content": _GEN_SYSTEM},
        {"role": "user", "content": f"ออกแบบ persona segments สำหรับ audience นี้: {prompt}"},
    ]
    last_error: Exception | None = None
    for attempt in range(2):  # retry 1 ครั้งเมื่อ parse/validate พัง (pattern LLM judge)
        result = adapter.chat(ModelTier.ANALYST, messages, max_tokens=1800, temperature=0)
        try:
            segments = _parse_segments(result.text)
            # normalize share ให้รวม 1.0 พอดี (model มักคลาดเคลื่อนทศนิยม) ก่อนเข้าด่าน validate
            total = sum(float(s.get("share", 0)) for s in segments) or 1.0
            for s in segments:
                s["share"] = round(float(s.get("share", 0)) / total, 4)
            drift = 1.0 - sum(s["share"] for s in segments)
            if segments:
                segments[0]["share"] = round(segments[0]["share"] + drift, 4)
            validate_pack(label, segments)
            return segments
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            last_error = e
            if attempt == 0:
                messages.append({"role": "assistant", "content": result.text[:2000]})
                messages.append(
                    {
                        "role": "user",
                        "content": f"ผลลัพธ์ไม่ผ่านการตรวจ: {e} — ตอบใหม่เป็น JSON ตาม schema เท่านั้น",
                    }
                )
    raise ValueError(f"generate persona pack ไม่สำเร็จหลัง retry: {last_error}")


def try_ask(segment: dict, question: str, *, adapter: LLMAdapter | None = None) -> str:
    """ให้ segment เดียวตอบ 1 คำถาม — preview ราคาถูกก่อนเผางบรันเต็ม (crowd, reasoning=False)"""
    adapter = adapter or _make_adapter()
    priors = segment.get("cultural_priors", {})
    persona_desc = (
        f"คุณคือคนไทยกลุ่ม '{segment.get('name', 'ทั่วไป')}' "
        f"(เกรงใจ {priors.get('kreng_jai', 0.5):.1f}, "
        f"ช่องว่างพูด-ทำ {priors.get('say_do_gap', 0.5):.1f}, "
        f"ใช้มีม/ประชด {priors.get('sarcasm_meme', 0.5):.1f}) "
        f"ลักษณะ: {', '.join(segment.get('traits', [])) or 'ไม่ระบุ'}"
    )
    result = adapter.chat(
        ModelTier.CROWD,
        [
            {
                "role": "system",
                "content": persona_desc + " ตอบภาษาไทยเท่านั้น ตอบสั้นๆ 1-2 ประโยคตามมุมมองของกลุ่มคุณ "
                "ห้ามกุชื่อ/ตัวเลข — จำไม่ได้ให้บอกว่าไม่แน่ใจ เรียกคนด้วยบทบาท",
            },
            {"role": "user", "content": question},
        ],
        max_tokens=200,
        reasoning=False,
    )
    return sanitize_llm_text(result.text)
