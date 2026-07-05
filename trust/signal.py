"""Sim-to-Signal (SIG-01/03/04) — แปลงผลจำลองเป็น feature เชิงปริมาณพร้อมช่วงความเชื่อมั่น

ทุก feature คำนวณจากกลไกจริงของ engine (per-seed แล้วรวมเป็น mean + CI95) ไม่ใช่ให้ LLM เดา:
- narrative_momentum: อัตราเพิ่มของสัดส่วนผู้เชื่อช่วงท้าย run (ต่อ round)
- narrative_dispersion: ส่วนเบี่ยงเบนมาตรฐานของ belief rate ระหว่าง segment
- consensus_fragility: Fragility Index จาก multiverse (0-1)
- sentiment_divergence: |belief ของผู้แสดงออก − belief ของประชากรทั้งหมด| (voice ≠ population)
- contrarian_pressure: สัดส่วนผู้ได้ยินแต่ "ไม่เชื่อ"
- adoption_elasticity: conversion ได้ยิน→เชื่อ

SIG-03: ทุก bundle ฝัง metadata บังคับ (run id, fragility, calibration โดเมน, provenance hash)
SIG-04: disclaimer เชิงโครงสร้าง + ห้ามใช้เป็น real-time trading signal
"""

import hashlib
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from simulation.engine import RunResult
from trust.universe import FragilityReport

DISCLAIMER = (
    "simulation_estimate — feature จากโลกจำลอง ไม่ใช่สัญญาณซื้อขาย ห้ามใช้เป็น "
    "real-time trading signal (ToS); ต้องผ่าน out-of-sample harness กับข้อมูลจริงของคุณก่อนใช้"
)


@dataclass(frozen=True)
class SignalFeature:
    name: str
    mean: float
    ci95: tuple[float, float]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mean": round(self.mean, 4),
            "ci95": [round(x, 4) for x in self.ci95],
        }


def _belief_share_at(result: RunResult, msg_id: str, round_no: int) -> float:
    n = len(result.states)
    return (
        sum(
            1
            for st in result.states.values()
            if st.believed.get(msg_id) and st.heard.get(msg_id, 10**9) <= round_no
        )
        / n
    )


def features_for_run(result: RunResult, msg_id: str, *, rounds: int) -> dict[str, float]:
    """feature ต่อหนึ่ง seed-run — คำนวณจาก state/trail จริงทั้งหมด"""
    states = result.states.values()
    n = len(result.states)
    heard = [st for st in states if msg_id in st.heard]
    believed_all = sum(1 for st in states if st.believed.get(msg_id))

    tail = max(1, rounds // 4)
    momentum = (
        _belief_share_at(result, msg_id, rounds) - _belief_share_at(result, msg_id, rounds - tail)
    ) / tail

    seg_rates: dict[str, list[bool]] = defaultdict(list)
    for st in states:
        seg_rates[st.persona.segment_name].append(bool(st.believed.get(msg_id)))
    rates = [sum(v) / len(v) for v in seg_rates.values()]
    dispersion = statistics.pstdev(rates) if len(rates) > 1 else 0.0

    expressors = result.expressors()
    exp_believers = sum(1 for a in expressors if result.states[a].believed.get(msg_id))
    exp_rate = exp_believers / len(expressors) if expressors else 0.0
    divergence = abs(exp_rate - believed_all / n)

    contrarian = (
        sum(1 for st in heard if not st.believed.get(msg_id)) / len(heard) if heard else 0.0
    )
    adoption = believed_all / len(heard) if heard else 0.0

    return {
        "narrative_momentum": momentum,
        "narrative_dispersion": dispersion,
        "sentiment_divergence": divergence,
        "contrarian_pressure": contrarian,
        "adoption_elasticity": adoption,
    }


def _ci95(values: list[float]) -> tuple[float, float]:
    mean = statistics.fmean(values)
    if len(values) < 2:
        return (mean, mean)
    sd = statistics.stdev(values)
    half = 1.96 * sd / (len(values) ** 0.5)
    return (mean - half, mean + half)


@dataclass(frozen=True)
class SignalBundle:
    features: tuple[SignalFeature, ...]
    run_id: str
    fragility_index: int
    calibration_note: str
    provenance_hash: str
    model_version: str

    def to_dict(self) -> dict:
        return {
            "features": [f.to_dict() for f in self.features],
            "metadata": {  # SIG-03: บังคับครบทุก response
                "run_id": self.run_id,
                "fragility_index": self.fragility_index,
                "calibration": self.calibration_note,
                "provenance_hash": self.provenance_hash,
                "model_version": self.model_version,
            },
            "disclaimer": DISCLAIMER,  # SIG-04: เชิงโครงสร้าง ลบไม่ได้
        }


def build_signal_bundle(
    results: list[RunResult],
    msg_id: str,
    *,
    rounds: int,
    fragility: FragilityReport,
    run_id: str,
    calibration_note: str,
    model_version: str,
    provenance_source: Path | str,
) -> SignalBundle:
    per_seed = [features_for_run(r, msg_id, rounds=rounds) for r in results]
    names = list(per_seed[0])
    features = [
        SignalFeature(
            name=name,
            mean=statistics.fmean([p[name] for p in per_seed]),
            ci95=_ci95([p[name] for p in per_seed]),
        )
        for name in names
    ]
    features.append(
        SignalFeature(
            name="consensus_fragility",
            mean=fragility.fragility_index / 100,
            ci95=(fragility.fragility_index / 100, fragility.fragility_index / 100),
        )
    )
    provenance_hash = hashlib.sha256(Path(provenance_source).read_bytes()).hexdigest()[:16]
    return SignalBundle(
        features=tuple(features),
        run_id=run_id,
        fragility_index=fragility.fragility_index,
        calibration_note=calibration_note,
        provenance_hash=provenance_hash,
        model_version=model_version,
    )
