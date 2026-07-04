"""Thai mini-benchmark — รันชุดคำถาม data/benchmark/thai_mini.yaml กับ model หลายตัวบน OpenRouter

ใช้คัดเลือก crowd model ตามเงื่อนไขทบทวนใน ADR-0001 (ต้องมี .env ที่มี LLM_BASE_URL/LLM_API_KEY ก่อน)

    uv run python scripts/thai_benchmark.py --models qwen/qwen-flash qwen/qwen-turbo
    # ผลลัพธ์: .tmp/benchmark-<timestamp>.md ให้ human review แล้วบันทึกคะแนนลง ADR-0001

ต้นทุนโดยประมาณ: 12 ข้อ × N models × ~1K token/ข้อ — ต่ำกว่า $0.10 ต่อ model ที่ราคา flash-tier
"""

import argparse
from datetime import datetime
from pathlib import Path

import yaml
from openai import OpenAI

from core.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "data" / "benchmark" / "thai_mini.yaml"
OUT_DIR = ROOT / ".tmp"


def main() -> None:
    parser = argparse.ArgumentParser(description="Thai mini-benchmark สำหรับคัดเลือก crowd model")
    parser.add_argument("--models", nargs="+", required=True, help="model slugs บน OpenRouter")
    parser.add_argument("--max-tokens", type=int, default=400)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_base_url:
        raise SystemExit("ยังไม่ได้ตั้งค่า LLM_BASE_URL/LLM_API_KEY ใน .env — เติมก่อนรัน benchmark")

    client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, max_retries=3)
    questions = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"benchmark-{datetime.now():%Y%m%d-%H%M%S}.md"

    lines = [
        "# ผล Thai mini-benchmark",
        f"- วันที่: {datetime.now():%Y-%m-%d %H:%M}",
        f"- models: {', '.join(args.models)}",
        "- วิธีให้คะแนน: อ่านคำตอบเทียบ `expect` ให้ 0 (พลาด) / 1 (พอใช้) / 2 (ดี) ต่อข้อ",
        "- บันทึกคะแนนสรุปลง docs/adr/ADR-0001 หลัง review",
        "",
    ]
    for q in questions:
        lines += [f"## [{q['category']}] {q['id']}", "", f"**โจทย์:** {q['prompt'].strip()}", ""]
        lines += [f"**เกณฑ์:** {q['expect'].strip()}", ""]
        for model in args.models:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": q["prompt"]}],
                max_tokens=args.max_tokens,
            )
            answer = (response.choices[0].message.content or "").strip()
            lines += [f"### {model}", "", answer, "", "**คะแนน (เติมเอง):** __ /2", ""]
        print(f"done: {q['id']}")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nผลลัพธ์: {out_path}")


if __name__ == "__main__":
    main()
