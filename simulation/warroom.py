"""Live War Room + Divergence Alarm (REH-04/05 + SIM-11)

วงจรช่วงวิกฤต: อ่านข้อมูลจริงระดับ aggregate → sync โลกจำลองให้ตรงค่าที่สังเกต →
simulate ล่วงหน้า 48 ชม. (หลาย seed = ซอง envelope ของ scenario) → รอบถัดไปเทียบ
ค่าจริงใหม่กับ envelope — **โลกจริงหลุดซอง = Divergence Alarm** (REH-05):
สัญญาณว่ามีตัวแปรที่โลกจำลองยังไม่ถูก model ไม่ใช่แค่ความคลาดเคลื่อน

Governance:
- SIM-11: การอ่าน feed คือ external retrieval — ทุกครั้งต้องผ่าน
  `ensure_external_retrieval_allowed(ctx)` (hindcast_mode = block ตาย, กฎเหล็กข้อ 2)
- GOV-01: note ใน feed เป็นข้อความนำเข้า — ผ่าน PII detector, พบ = block ทั้ง feed
- feed เป็นค่าสถิติ aggregate เท่านั้น (สัดส่วน 0-1) ห้ามข้อมูลรายบุคคล
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.run_context import RunContext, ensure_external_retrieval_allowed
from governance.pii import PIIDetector
from simulation.engine import FabricSimulation, Message
from simulation.persona import Persona

HOURS_PER_ROUND = 4  # 1 round ของ engine ≈ 4 ชม. → 48 ชม. = 12 rounds
FORECAST_ROUNDS = 12
DIVERGENCE_TOLERANCE = 0.02  # เผื่อ noise เล็กน้อยก่อนนับว่า "หลุดซอง"


class FeedBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class Observation:
    t_hour: int  # ชั่วโมงสัมพัทธ์นับจากเริ่ม incident
    metric: str  # เช่น "belief_share" — สัดส่วนประชากรที่เชื่อ/ติด narrative (aggregate)
    value: float  # 0-1
    note: str = ""


@dataclass(frozen=True)
class Forecast:
    made_at_hour: int
    base_value: float
    # envelope[i] = (lo, hi) ของ belief share ที่ +(i+1)*4 ชม. จากตอนพยากรณ์
    envelope: tuple[tuple[float, float], ...]

    def bounds_at(self, t_hour: int) -> tuple[float, float] | None:
        """ซองพยากรณ์ ณ ชั่วโมง t (absolute) — None ถ้าเกินขอบฟ้า 48 ชม."""
        steps = round((t_hour - self.made_at_hour) / HOURS_PER_ROUND)
        if steps < 1 or steps > len(self.envelope):
            return None
        return self.envelope[steps - 1]


@dataclass(frozen=True)
class DivergenceResult:
    observation: Observation
    bounds: tuple[float, float] | None
    score: float  # ระยะที่หลุดนอกซอง (0 = อยู่ในซอง)

    @property
    def alarm(self) -> bool:
        return self.score > DIVERGENCE_TOLERANCE


def load_feed(path: Path | str, ctx: RunContext, detector: PIIDetector) -> list[Observation]:
    """อ่าน feed aggregate — SIM-11 gate + PII check ทุก note (fail-closed)"""
    ensure_external_retrieval_allowed(ctx)  # กฎเหล็กข้อ 2: hindcast = block ตาย
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    observations = []
    for row in raw["observations"]:
        note = str(row.get("note", ""))
        if note:
            report = detector.check(note)
            if report.blocked:
                raise FeedBlockedError(
                    f"feed ถูก block: พบ PII ใน note ที่ t={row['t_hour']} (GOV-01) — "
                    + "; ".join(report.block_reasons)
                )
        value = float(row["value"])
        if not 0.0 <= value <= 1.0:
            raise FeedBlockedError(
                f"ค่า {value} ที่ t={row['t_hour']} นอกช่วง 0-1 — feed ต้องเป็นสัดส่วน aggregate"
            )
        observations.append(
            Observation(
                t_hour=int(row["t_hour"]), metric=str(row["metric"]), value=value, note=note
            )
        )
    return sorted(observations, key=lambda o: o.t_hour)


def _preseed_believers(personas: list[Persona], share: float) -> set[str]:
    """เลือก agent ที่ 'เชื่อแล้ว' ให้สัดส่วนตรงค่าที่สังเกต — deterministic (เรียงตาม id)"""
    k = round(share * len(personas))
    return {p.agent_id for p in sorted(personas, key=lambda p: p.agent_id)[:k]}


def forecast_48h(
    personas: list[Persona],
    narrative_text: str,
    observed: Observation,
    *,
    base_seed: int,
    n_seeds: int = 5,
) -> Forecast:
    """sync โลกจำลองที่ค่าจริงล่าสุด แล้วรันล่วงหน้า 12 rounds (48 ชม.) หลาย seed → envelope"""
    per_seed_paths: list[list[float]] = []
    believers = _preseed_believers(personas, observed.value)
    for s in range(n_seeds):
        sim = FabricSimulation(personas, seed=base_seed + s)
        sim.preseed(Message("narrative", "rumor", narrative_text, 0, "public_feed"), believers)
        path: list[float] = []
        # วัด share สะสมทีละ round — รัน run(1) ต่อเนื่องไม่ได้ (run เดินจาก round 1 เสมอ)
        # จึงรันเต็มแล้วอ่าน trail: believed ณ round r = preseed + ผู้เชื่อที่ heard ≤ r
        result = sim.run(FORECAST_ROUNDS)
        n = len(result.states)
        for r in range(1, FORECAST_ROUNDS + 1):
            believing = sum(
                1
                for st in result.states.values()
                if st.believed.get("narrative") and st.heard.get("narrative", 99) <= r
            )
            path.append(believing / n)
        per_seed_paths.append(path)
    envelope = tuple(
        (min(p[i] for p in per_seed_paths), max(p[i] for p in per_seed_paths))
        for i in range(FORECAST_ROUNDS)
    )
    return Forecast(made_at_hour=observed.t_hour, base_value=observed.value, envelope=envelope)


def check_divergence(forecast: Forecast, actual: Observation) -> DivergenceResult:
    bounds = forecast.bounds_at(actual.t_hour)
    if bounds is None:
        return DivergenceResult(observation=actual, bounds=None, score=0.0)
    lo, hi = bounds
    score = max(0.0, lo - actual.value, actual.value - hi)
    return DivergenceResult(observation=actual, bounds=bounds, score=round(score, 4))


def render_warroom_report(
    title: str,
    narrative_text: str,
    forecasts: list[Forecast],
    divergences: list[DivergenceResult],
) -> str:
    any_alarm = any(d.alarm for d in divergences)
    lines = [
        f"# War Room Report (REH-04/05): {title}",
        "",
        "> ⚠️ simulation_estimate — envelope จากโลกจำลอง ≤ 10 agents (cap ช่วงพัฒนา) "
        "ใช้บอกทิศทาง ไม่ใช่พยากรณ์รับประกัน",
        "",
        f"- narrative ที่ติดตาม: {narrative_text}",
        f"- รอบพยากรณ์: {len(forecasts)} | จุดตรวจ divergence: {len(divergences)}",
        "",
    ]
    if any_alarm:
        lines += [
            "## 🚨 DIVERGENCE ALARM (REH-05)",
            "",
            "โลกจริงเบี่ยงออกนอกทุก scenario ที่จำลองไว้ — **มีตัวแปรที่ยังไม่ถูก model** "
            "ให้ทบทวนสมมติฐาน/หาข้อมูลใหม่ทันที อย่าเชื่อพยากรณ์เดิมต่อ",
            "",
        ]
    lines += [
        "| เวลา (ชม.) | ค่าจริง | ซองพยากรณ์ | หลุดซอง | สถานะ |",
        "|---|---|---|---|---|",
    ]
    for d in divergences:
        bounds_txt = f"[{d.bounds[0]:.0%}, {d.bounds[1]:.0%}]" if d.bounds else "(เกินขอบฟ้า)"
        status = "🚨 ALARM" if d.alarm else "ปกติ"
        lines.append(
            f"| t+{d.observation.t_hour} | {d.observation.value:.0%} | {bounds_txt} "
            f"| {d.score:.1%} | {status} |"
        )
    lines += ["", "## Envelope พยากรณ์ 48 ชม. รายรอบ", ""]
    for f in forecasts:
        lo12, hi12 = f.envelope[-1]
        lines.append(
            f"- พยากรณ์ ณ t+{f.made_at_hour} (ฐาน {f.base_value:.0%}): "
            f"อีก 48 ชม. คาดอยู่ในช่วง [{lo12:.0%}, {hi12:.0%}]"
        )
    return "\n".join(lines)
