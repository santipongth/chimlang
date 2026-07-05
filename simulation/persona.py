"""Persona factory (SIM-02) — สร้าง agent population จาก data/samples/population/segments.yaml

- สัดส่วน segment ตาม share (largest remainder ให้ n เล็กยังรักษาสัดส่วน)
- cultural priors (เกรงใจ / say-do gap / ประชด) + voice_activity + channel mix ต่อตัว (FAB-02/05)
- cap guard: เกิน max_agents_dev = ปฏิเสธ (คำสั่งผู้ใช้ — ดู AGENTS.md)
"""

from dataclasses import dataclass
from pathlib import Path
from random import Random

import yaml

DEFAULT_SEGMENTS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "samples" / "population" / "segments.yaml"
)


class AgentCapExceededError(RuntimeError):
    def __init__(self, requested: int, cap: int):
        super().__init__(
            f"ขอ {requested} agents แต่ข้อจำกัดช่วงพัฒนาอยู่ที่ {cap} "
            "(คำสั่งผู้ใช้ 5 ก.ค. 2026 — ต้องได้รับอนุญาตจากผู้ใช้ก่อนเกิน)"
        )


@dataclass(frozen=True)
class Persona:
    agent_id: str
    segment_id: str
    segment_name: str
    channel_mix: dict[str, float]  # channel -> weight (รวม 1.0)
    voice_activity: float  # แนวโน้มแสดงออก (TRUST-07: ผู้แสดงออก vs ผู้สังเกตการณ์)
    kreng_jai: float
    say_do_gap: float
    sarcasm_meme: float
    traits: tuple[str, ...]


class PersonaFactory:
    def __init__(self, segments_path: Path | str = DEFAULT_SEGMENTS_PATH, *, segments=None):
        if segments is not None:
            self.segments = segments
        else:
            raw = yaml.safe_load(Path(segments_path).read_text(encoding="utf-8"))
            self.segments = raw["segments"]
        total = sum(s["share"] for s in self.segments)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"share ของ segments รวมได้ {total} ต้องเป็น 1.0")

    def perturb_shares(self, *, seed: int, pct: float = 0.10) -> "PersonaFactory":
        """สร้าง factory ใหม่ที่สัดส่วน segment ถูกเขย่า ±pct แล้ว normalize (TRUST-04)

        deterministic ต่อ seed — ใช้สร้าง parallel universe ที่สมมติฐาน population ต่างกันเล็กน้อย
        """
        rng = Random(seed)
        jittered = [
            {**s, "share": max(0.005, s["share"] * (1 + rng.uniform(-pct, pct)))}
            for s in self.segments
        ]
        total = sum(s["share"] for s in jittered)
        for s in jittered:
            s["share"] = s["share"] / total
        return PersonaFactory(segments=jittered)

    def allocate(self, n: int) -> dict[str, int]:
        """แบ่งจำนวน agent ต่อ segment แบบ largest remainder — deterministic"""
        quotas = [(s["id"], s["share"] * n) for s in self.segments]
        counts = {sid: int(q) for sid, q in quotas}
        remainder = n - sum(counts.values())
        by_frac = sorted(quotas, key=lambda x: (x[1] - int(x[1]), x[0]), reverse=True)
        for sid, _ in by_frac[:remainder]:
            counts[sid] += 1
        return counts

    def sample(self, n: int, *, seed: int, max_agents: int) -> list[Persona]:
        if n > max_agents:
            raise AgentCapExceededError(n, max_agents)
        rng = Random(seed)
        counts = self.allocate(n)
        segment_by_id = {s["id"]: s for s in self.segments}
        personas: list[Persona] = []
        for sid, count in counts.items():
            seg = segment_by_id[sid]
            priors = seg["cultural_priors"]
            for i in range(count):
                # กระจายค่ารอบ prior ของ segment เล็กน้อย (±0.1) ให้ตัว agent ไม่โคลนกันเป๊ะ
                jitter = lambda v: min(1.0, max(0.0, v + rng.uniform(-0.1, 0.1)))  # noqa: E731
                personas.append(
                    Persona(
                        agent_id=f"{sid}-{i:02d}",
                        segment_id=sid,
                        segment_name=seg["name"],
                        channel_mix=dict(seg["channel_mix"]),
                        voice_activity=jitter(seg["voice_activity"]),
                        kreng_jai=jitter(priors["kreng_jai"]),
                        say_do_gap=jitter(priors["say_do_gap"]),
                        sarcasm_meme=jitter(priors["sarcasm_meme"]),
                        traits=tuple(seg.get("traits") or ()),
                    )
                )
        return personas
