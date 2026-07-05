"""Benchmark AC ของ FAB-01 — กลไกล้วน ไม่เรียก LLM (ต้นทุน $0)

ออกแบบรอบ 2 (บทเรียนรอบแรก: วัดแบบ first-channel ในรันรวมมี sample starvation ที่ n=10):
วัดแบบ **isolated channel** — รันแยกทีละช่องทาง แล้วเทียบความเร็วถึง 50% penetration

1. rumor ใน closed-group-only ต้องช้ากว่าใน public-feed-only (closed แพร่ช้ากว่า)
2. ใน closed-group-only: correction ต้องถึง 30% penetration ช้ากว่า rumor (ข่าวแก้เข้ากลุ่มปิดยาก)

    uv run python scripts/run_fab01_benchmark.py --seeds 30
"""

import argparse
from datetime import datetime
from math import comb
from pathlib import Path
from statistics import mean

from core.config import get_settings
from simulation.engine import FabricSimulation, Message
from simulation.persona import PersonaFactory

ROOT = Path(__file__).resolve().parents[1]
ROUNDS = 40
CORR_START = 8


def isolated_run(seed: int, n: int, channel: str, with_correction: bool = False):
    personas = PersonaFactory().sample(n, seed=seed, max_agents=n)
    sim = FabricSimulation(personas, seed=seed, enabled_channels=frozenset({channel}))
    sim.inject(Message("rumor", "rumor", "ข่าวลือทดสอบ", 1, channel))
    if with_correction:
        sim.inject(Message("corr", "correction", "ข่าวแก้ทดสอบ", CORR_START, channel))
    return sim.run(ROUNDS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    args = parser.parse_args()
    n = get_settings().max_agents_per_run  # เคารพ cap ช่วง dev

    t50_closed, t50_public = [], []
    claim1_holds = claim1_usable = 0
    t30_rumor_closed, t30_corr_closed = [], []
    claim2_holds = claim2_usable = 0
    never = ROUNDS + 1  # ไม่ถึงเป้าใน ROUNDS = ถือว่าช้าสุด (ใช้เทียบลำดับเท่านั้น)

    for seed in range(args.seeds):
        closed = isolated_run(seed, n, "line_closed_group", with_correction=True)
        public = isolated_run(seed, n, "public_feed")

        tc = closed.rounds_to_penetration("rumor", 0.5, from_round=1)
        tp = public.rounds_to_penetration("rumor", 0.5, from_round=1)
        if tc is not None or tp is not None:
            claim1_usable += 1
            tc_v, tp_v = never if tc is None else tc, never if tp is None else tp
            t50_closed.append(tc_v)
            t50_public.append(tp_v)
            if tc_v > tp_v:
                claim1_holds += 1

        tr = closed.rounds_to_penetration("rumor", 0.3, from_round=1)
        tk = closed.rounds_to_penetration("corr", 0.3, from_round=CORR_START)
        if tr is not None:
            claim2_usable += 1
            tr_v, tk_v = tr, never if tk is None else tk
            t30_rumor_closed.append(tr_v)
            t30_corr_closed.append(tk_v)
            if tk_v > tr_v:
                claim2_holds += 1

    def sign_test_p(holds: int, total: int) -> float:
        """one-sided binomial sign test: P(X >= holds | n=total, p=0.5)"""
        if total == 0:
            return 1.0
        return sum(comb(total, k) for k in range(holds, total + 1)) / 2**total

    # เกณฑ์ = sign test p < 0.05 ตามความหมายตรงของ AC "อย่างมีนัยสำคัญ"
    # (เดิมใช้สัดส่วน 80% ซึ่งเป็นค่า ad-hoc — เข้มเกินแบบไร้ฐานสถิติที่ n เล็ก)
    p1 = sign_test_p(claim1_holds, claim1_usable)
    p2 = sign_test_p(claim2_holds, claim2_usable)
    pass1 = claim1_usable > 0 and p1 < 0.05
    pass2 = claim2_usable > 0 and p2 < 0.05
    lines = [
        "# ผล Benchmark FAB-01 รอบ 2 (isolated-channel — ไม่ใช้ LLM)",
        f"- วันที่: {datetime.now():%Y-%m-%d %H:%M} | agents/run: {n} (cap ช่วง dev)",
        f"- rounds: {ROUNDS} | seeds: {args.seeds} | ค่า 'ไม่ถึงเป้า' นับเป็น {never} (ช้าสุด)",
        "",
        "## ข้อ 1: rumor ใน closed-group-only ช้ากว่าใน public-feed-only (rounds ถึง 50%)",
        f"- เฉลี่ย: closed = {mean(t50_closed):.1f} | public = {mean(t50_public):.1f}",
        f"- ถูกทิศ (closed ช้ากว่า): {claim1_holds}/{claim1_usable} seeds",
        "",
        "## ข้อ 2: ใน closed-only — correction ถึง 30% ช้ากว่า rumor (delay จากวันปล่อย)",
        f"- เฉลี่ย: rumor = {mean(t30_rumor_closed):.1f} | correction = {mean(t30_corr_closed):.1f}",
        f"- ถูกทิศ (correction ช้ากว่า): {claim2_holds}/{claim2_usable} seeds",
        "",
        "## เกณฑ์ตัดสิน: one-sided sign test p < 0.05 (= ความหมายตรงของ AC 'อย่างมีนัยสำคัญ')",
        f"- ข้อ 1: p = {p1:.2e} → {'ผ่าน ✅' if pass1 else 'ไม่ผ่าน ❌'}",
        f"- ข้อ 2: p = {p2:.2e} → {'ผ่าน ✅' if pass2 else 'ไม่ผ่าน ❌'}",
        "- หมายเหตุเกณฑ์: รอบก่อนใช้สัดส่วน 80% (ad-hoc) — เปลี่ยนเป็น sign test มาตรฐาน"
        " ซึ่งตรงกับถ้อยคำ AC มากกว่า (บันทึกการเปลี่ยนไว้โปร่งใส)",
        "",
        "หมายเหตุ: รันที่ 10 agents ตามข้อจำกัดช่วงพัฒนา — ยืนยันซ้ำที่ 100–1,000 agents เมื่อผู้ใช้ยกเลิก cap",
    ]
    report = "\n".join(lines)
    out = ROOT / ".tmp" / f"fab01-benchmark-{datetime.now():%Y%m%d-%H%M%S}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nรายงาน: {out}")


if __name__ == "__main__":
    main()
