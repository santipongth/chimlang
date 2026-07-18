"""Fabric calibration harness (ADR-0022) — วัดพฤติกรรม engine จริง + sensitivity ($0, ไม่มี LLM)

รัน:  uv run python scripts/calibrate_fabric.py
ผล:  .tmp/fabric-calibration.json (ดิบ) + พิมพ์สรุป markdown ลง stdout
     (รายงาน canonical: docs/reports/core-engine-audit-2026-07.md)

วัดอะไร:
1. Penetration/belief/latency/mutation ของ scenario มาตรฐาน (rumor + คำชี้แจง broadcast
   แบบ ADR-0003) ที่ n=100 และ n=1000, 5 seeds — ยืนยัน invariant: delta ของคำชี้แจง
   ต้องติดลบ (ลดผู้เชื่อข่าวลือ) และ scale-invariant โดยประมาณ
2. FAB-01 latency invariant: isolated closed group ต้องแพร่ช้ากว่า public feed
3. Re-exposure (กลไกใหม่): สัดส่วน reexposed events และผลต่อ belief
4. Sensitivity: perturb พารามิเตอร์กลไกทีละตัว ±20% → จัดอันดับว่า headline outcome
   (correction delta) ไวต่อตัวไหนสุด = ลำดับความสำคัญของการ calibrate กับข้อมูลจริง (FAB-05)
"""

import json
import statistics
from dataclasses import replace
from pathlib import Path

import simulation.channels as channels_mod
import simulation.engine as engine_mod
from simulation.channels import CHANNELS, ChannelParams
from simulation.engine import FabricSimulation, Message
from simulation.persona import PersonaFactory
from simulation.tipping import belief_series, tipping_from_run

RUMOR = "ลือว่ามาตรการใหม่จะเก็บค่าธรรมเนียมเพิ่มสามเท่าและมีผลทันที"
CORRECTION = "หน่วยงานชี้แจง: อัตราคงเดิม มีผลปีหน้า พร้อมช่วงรับฟังความเห็น"
ROUNDS = 30
CORRECTION_ROUND = 8
BROADCAST_SHARE = 0.2  # ADR-0003: คำชี้แจงทางการปล่อยแบบสื่อมวลชน
MUTATION_RATE = 0.15
SEEDS = (42, 43, 44, 45, 46)


PRESEED_SHARE = 0.10  # ADR-0003: ข่าวลือระดับเมืองเริ่มจากผู้เชื่อ 10% ไม่ใช่ seeder เดี่ยว


def _run(n: int, seed: int, *, with_correction: bool, enabled=None):
    from random import Random

    personas = PersonaFactory().sample(n, seed=seed, max_agents=n)
    sim = FabricSimulation(
        personas, seed=seed, enabled_channels=enabled, rumor_mutation_rate=MUTATION_RATE
    )
    rumor = Message("rumor", "rumor", RUMOR, 0, "public_feed")
    believer_ids = set(
        Random(f"{seed}:preseed").sample(
            [p.agent_id for p in personas], max(1, int(n * PRESEED_SHARE))
        )
    )
    sim.preseed(rumor, believer_ids)
    if with_correction:
        sim.inject(
            Message(
                "official",
                "correction",
                CORRECTION,
                CORRECTION_ROUND,
                "public_feed",
                counters="rumor",
                broadcast_share=BROADCAST_SHARE,
            )
        )
    return sim.run(ROUNDS)


def _belief_share(result, msg_id: str) -> float:
    return belief_series(result, msg_id)[-1]


def scenario_metrics(n: int, seed: int) -> dict:
    base = _run(n, seed, with_correction=False)
    corr = _run(n, seed, with_correction=True)
    reexposed = sum(1 for e in corr.trail if e["action"] == "reexposed")
    heard_events = sum(1 for e in corr.trail if e["action"] == "heard")
    channel_first = {c: len(r) for c, r in corr.first_heard_by_channel("rumor").items()}
    return {
        "n": n,
        "seed": seed,
        "rumor_penetration": round(corr.penetration("rumor"), 4),
        "rumor_belief_baseline": round(_belief_share(base, "rumor"), 4),
        "rumor_belief_with_correction": round(_belief_share(corr, "rumor"), 4),
        "correction_delta": round(_belief_share(corr, "rumor") - _belief_share(base, "rumor"), 4),
        "correction_reach": round(corr.penetration("official"), 4),
        "mutation_share": round(corr.mutation_share("rumor"), 4),
        "tipping_points": len(tipping_from_run(corr, "rumor")),
        "first_heard_by_channel": channel_first,
        "reexposed_events": reexposed,
        "reexposed_per_heard": round(reexposed / max(1, heard_events), 4),
        "expressors": len(corr.expressors()),
        "observers": len(corr.observers()),
    }


def latency_invariant(seed: int, n: int = 100) -> dict:
    """FAB-01: closed group ต้องช้ากว่า public feed (isolated-channel, preseed 10% เท่ากัน)"""
    from random import Random

    out = {}
    for channel in ("line_closed_group", "public_feed"):
        personas = PersonaFactory().sample(n, seed=seed, max_agents=n)
        sim = FabricSimulation(personas, seed=seed, enabled_channels=frozenset({channel}))
        rumor = Message("rumor", "rumor", RUMOR, 0, channel)
        believers = set(
            Random(f"{seed}:preseed").sample(
                [p.agent_id for p in personas], max(1, int(n * PRESEED_SHARE))
            )
        )
        sim.preseed(rumor, believers)
        result = sim.run(ROUNDS)
        out[channel] = result.rounds_to_penetration("rumor", 0.5, from_round=0)
    return out


def _perturbed_channels(param_key: str, factor: float) -> dict[str, ChannelParams]:
    channel, field_name = param_key.split(".")
    original = CHANNELS[channel]
    return {
        **CHANNELS,
        channel: replace(original, **{field_name: getattr(original, field_name) * factor}),
    }


def sensitivity(n: int = 200, seeds=(42, 43, 44)) -> list[dict]:
    """|Δ correction_delta| เมื่อ perturb พารามิเตอร์ ±20% — เรียงจากไวมากไปน้อย"""

    def headline(seed: int) -> float:
        base = _run(n, seed, with_correction=False)
        corr = _run(n, seed, with_correction=True)
        return _belief_share(corr, "rumor") - _belief_share(base, "rumor")

    reference = statistics.mean(headline(s) for s in seeds)
    channel_params = [
        f"{ch}.{field_name}"
        for ch in CHANNELS
        for field_name in ("base_rate", "trust", "correction_factor")
    ]
    module_constants = [
        ("channels.VIRALITY_BOOST", channels_mod, "VIRALITY_BOOST"),
        ("channels.ALGO_TREND_THRESHOLD", channels_mod, "ALGO_TREND_THRESHOLD"),
        ("engine.SAY_DO_CLOSED_BOOST", engine_mod, "SAY_DO_CLOSED_BOOST"),
        ("engine.KRENG_JAI_PUBLIC_SUPPRESS", engine_mod, "KRENG_JAI_PUBLIC_SUPPRESS"),
        ("engine.KRENG_JAI_CORRECTION_SUPPRESS", engine_mod, "KRENG_JAI_CORRECTION_SUPPRESS"),
        ("engine.RECONSIDER_DECAY", engine_mod, "RECONSIDER_DECAY"),
    ]
    rows = []
    for key in channel_params:
        effects = []
        for factor in (0.8, 1.2):
            patched = _perturbed_channels(key, factor)
            saved = dict(CHANNELS)
            try:
                CHANNELS.clear()
                CHANNELS.update(patched)
                effects.append(statistics.mean(headline(s) for s in seeds) - reference)
            finally:
                CHANNELS.clear()
                CHANNELS.update(saved)
        rows.append({"param": key, "effect_minus20": effects[0], "effect_plus20": effects[1]})
    for label, module, attr in module_constants:
        original_value = getattr(module, attr)
        effects = []
        for factor in (0.8, 1.2):
            try:
                setattr(module, attr, original_value * factor)
                effects.append(statistics.mean(headline(s) for s in seeds) - reference)
            finally:
                setattr(module, attr, original_value)
        rows.append({"param": label, "effect_minus20": effects[0], "effect_plus20": effects[1]})
    for row in rows:
        row["max_abs_effect"] = round(max(abs(row["effect_minus20"]), abs(row["effect_plus20"])), 4)
        row["effect_minus20"] = round(row["effect_minus20"], 4)
        row["effect_plus20"] = round(row["effect_plus20"], 4)
    rows.sort(key=lambda r: -r["max_abs_effect"])
    return [{"reference_delta": round(reference, 4)}] + rows


def main() -> None:
    report = {"scenario": [], "latency_invariant": [], "sensitivity": []}
    for n in (100, 1000):
        for seed in SEEDS:
            report["scenario"].append(scenario_metrics(n, seed))
    for seed in SEEDS[:3]:
        report["latency_invariant"].append({"seed": seed, **latency_invariant(seed)})
    report["sensitivity"] = sensitivity()

    out = Path(".tmp/fabric-calibration.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    def _mean(rows, key):
        return round(statistics.mean(r[key] for r in rows), 4)

    for n in (100, 1000):
        rows = [r for r in report["scenario"] if r["n"] == n]
        print(
            f"n={n}: penetration {_mean(rows, 'rumor_penetration')} | "
            f"belief base {_mean(rows, 'rumor_belief_baseline')} → "
            f"with correction {_mean(rows, 'rumor_belief_with_correction')} "
            f"(delta {_mean(rows, 'correction_delta')}) | "
            f"mutation {_mean(rows, 'mutation_share')} | "
            f"reexposed/heard {_mean(rows, 'reexposed_per_heard')}"
        )
    for row in report["latency_invariant"]:
        print(
            f"latency seed {row['seed']}: closed {row['line_closed_group']} rounds "
            f"vs public {row['public_feed']} rounds (ต้อง closed > public)"
        )
    print("sensitivity (top 6 โดย |Δ correction_delta|):")
    for row in report["sensitivity"][1:7]:
        print(
            f"  {row['param']}: −20% → {row['effect_minus20']:+}, +20% → {row['effect_plus20']:+}"
        )
    print(f"\nดิบทั้งหมด: {out}")


if __name__ == "__main__":
    main()
