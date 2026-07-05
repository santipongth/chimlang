"""Simulation engine v1 (SIM-03 ระดับกลไกการแพร่) — round-based, deterministic ต่อ seed

ขอบเขต v1 (M3): พลวัตการแพร่/เชื่อ/แชร์ของข้อความผ่าน 4 ช่องทาง + reasoning trail
เชิงเหตุการณ์ครบทุก agent — ชั้น "agent เขียนโพสต์เอง" (LLM) อยู่ใน voice.py แยกต่างหาก
เพื่อคุมต้นทุน (ADR-0002)

พฤติกรรมเชิงวัฒนธรรม (FAB-02):
- เกรงใจ + say-do gap: ความเชื่อส่วนตัว (believed) กับการแสดงออก (shared) แยกกัน —
  agent เกรงใจสูงจะเชื่อแต่ไม่แชร์ในที่สาธารณะ แต่กล้าส่งต่อในกลุ่มปิดมากกว่า
"""

import uuid
from dataclasses import dataclass, field
from random import Random

from simulation.channels import CHANNELS, spread_pressure
from simulation.persona import Persona

GROUP_SIZE = 4  # ขนาดกลุ่ม LINE ต่อกลุ่ม (แบ่งตาม segment)


@dataclass(frozen=True)
class Message:
    msg_id: str
    kind: str  # rumor | correction
    text: str
    start_round: int
    seed_channel: str  # ช่องทางที่ข้อความถูกปล่อยครั้งแรก


@dataclass
class AgentState:
    persona: Persona
    heard: dict[str, int] = field(default_factory=dict)  # msg_id -> round แรกที่ได้ยิน
    heard_via: dict[str, str] = field(default_factory=dict)  # msg_id -> channel แรก
    believed: dict[str, bool] = field(default_factory=dict)
    sharing: dict[str, bool] = field(default_factory=dict)  # ยังแชร์ต่ออยู่ไหม


@dataclass(frozen=True)
class RunResult:
    run_id: str
    seed: int
    rounds: int
    states: dict[str, AgentState]
    trail: tuple[dict, ...]  # เหตุการณ์ทั้งหมด: {round, agent, msg, channel, action}

    def first_heard_by_channel(self, msg_id: str) -> dict[str, list[int]]:
        """round แรกที่ได้ยิน จัดกลุ่มตามช่องทางที่ส่งถึงเป็นช่องแรก"""
        out: dict[str, list[int]] = {}
        for st in self.states.values():
            if msg_id in st.heard:
                out.setdefault(st.heard_via[msg_id], []).append(st.heard[msg_id])
        return out

    def penetration(self, msg_id: str) -> float:
        return sum(1 for st in self.states.values() if msg_id in st.heard) / len(self.states)

    def rounds_to_penetration(self, msg_id: str, frac: float, *, from_round: int) -> int | None:
        """จำนวน round (นับจากวันปล่อย) กว่าข้อความจะถึง frac ของประชากร — None ถ้าไม่ถึง"""
        rounds_heard = sorted(st.heard[msg_id] for st in self.states.values() if msg_id in st.heard)
        target = int(len(self.states) * frac + 0.999)  # ceil
        if len(rounds_heard) < target or target == 0:
            return None
        return rounds_heard[target - 1] - from_round


class FabricSimulation:
    def __init__(
        self,
        personas: list[Persona],
        *,
        seed: int,
        enabled_channels: frozenset[str] | None = None,
    ):
        """enabled_channels: จำกัดช่องทาง (ใช้ทำ isolated-channel benchmark) — None = ครบ 4"""
        self._rng = Random(seed)
        self._seed = seed
        self._states = {p.agent_id: AgentState(persona=p) for p in personas}
        self._order = sorted(self._states)  # ลำดับ deterministic
        self._messages: list[Message] = []
        self._trail: list[dict] = []
        self._channels = {
            name: p
            for name, p in CHANNELS.items()
            if enabled_channels is None or name in enabled_channels
        }
        if not self._channels:
            raise ValueError("enabled_channels ไม่ตรงกับช่องทางที่มีอยู่")
        # channel mix ต่อ agent ถูก re-normalize บนช่องทางที่เปิด — เพื่อให้ benchmark
        # แบบ isolated วัด "พลวัตของช่องทาง" ไม่ใช่ "สัดส่วนความสนใจ" ของ agent
        self._mix: dict[str, dict[str, float]] = {}
        for aid in self._order:
            mix = self._states[aid].persona.channel_mix
            total = sum(mix.get(c, 0.0) for c in self._channels)
            self._mix[aid] = (
                {c: mix.get(c, 0.0) / total for c in self._channels}
                if total > 0
                else {c: 1.0 / len(self._channels) for c in self._channels}
            )
        # กลุ่ม LINE: agent อยู่ 2 กลุ่มข้าม segment (ครอบครัว + ที่ทำงาน/ชุมชน) —
        # บทเรียน benchmark 2 รอบ: กลุ่มตาม segment เล็กเกิน / กลุ่มเดียวเป็น clique
        # โดดๆ ไม่มีสะพานข้ามกลุ่ม ข่าวลือใน closed-only ตันที่กลุ่มแรก (ไม่ตรงความจริง)
        self._closed_contacts: dict[str, set[str]] = {a: set() for a in self._order}
        for salt in (0x5EED, 0xFA111):  # 2 partitions = small-world มีสะพานข้ามกลุ่ม
            shuffled = list(self._order)
            Random(seed ^ salt).shuffle(shuffled)  # RNG แยก ไม่กวน sequence หลัก
            for gi in range(0, len(shuffled), GROUP_SIZE):
                grp = shuffled[gi : gi + GROUP_SIZE]
                for m in grp:
                    self._closed_contacts[m] |= set(grp) - {m}

    def inject(self, message: Message) -> None:
        self._messages.append(message)

    def _neighbors(self, agent_id: str) -> list[str]:
        i = self._order.index(agent_id)
        return [self._order[j] for j in (i - 1, i + 1) if 0 <= j < len(self._order)]

    def _log(self, round_no: int, agent_id: str, msg: Message, channel: str, action: str) -> None:
        self._trail.append(
            {
                "round": round_no,
                "agent": agent_id,
                "msg": msg.msg_id,
                "channel": channel,
                "action": action,
            }
        )

    def _expose(self, round_no: int, st: AgentState, msg: Message, channel: str) -> None:
        st.heard[msg.msg_id] = round_no
        st.heard_via[msg.msg_id] = channel
        self._log(round_no, st.persona.agent_id, msg, channel, "heard")
        p = st.persona
        believe_prob = CHANNELS[channel].trust
        if msg.kind == "correction" and channel == "line_closed_group":
            # ข่าวแก้ในกลุ่มปิดถูกลดทอนด้วยความเกรงใจผู้ส่งเดิม (corpus 2026-06-08)
            believe_prob *= 1.0 - 0.5 * p.kreng_jai
        believed = self._rng.random() < believe_prob
        st.believed[msg.msg_id] = believed
        if believed:
            self._log(round_no, p.agent_id, msg, channel, "believed")
            share_prob = p.voice_activity
            if channel == "line_closed_group":
                # เกรงใจกดการแสดงออกสาธารณะ แต่ในกลุ่มปิดกล้าส่งต่อมากขึ้น (say-do gap)
                share_prob = min(1.0, share_prob + 0.4 * p.say_do_gap)
            else:
                share_prob *= 1.0 - 0.5 * p.kreng_jai
            if self._rng.random() < share_prob:
                st.sharing[msg.msg_id] = True
                self._log(round_no, p.agent_id, msg, channel, "shared")

    def run(self, rounds: int) -> RunResult:
        n = len(self._states)
        for round_no in range(1, rounds + 1):
            for msg in self._messages:
                if round_no < msg.start_round:
                    continue
                if round_no == msg.start_round:
                    # ปล่อยข้อความ: ผู้แชร์คนแรกคือ agent ที่ voice สูงสุดใน seed channel
                    seeder = max(
                        self._order,
                        key=lambda a: (
                            self._mix[a].get(msg.seed_channel, 0)
                            * self._states[a].persona.voice_activity
                        ),
                    )
                    self._expose(round_no, self._states[seeder], msg, msg.seed_channel)
                    self._states[seeder].sharing[msg.msg_id] = True
                    continue

                sharers = {a for a in self._order if self._states[a].sharing.get(msg.msg_id)}
                global_ratio = len(sharers) / n
                for aid in self._order:
                    st = self._states[aid]
                    if msg.msg_id in st.heard:
                        continue
                    contacts = self._closed_contacts[aid]
                    sharers_in_group = len(contacts & sharers)
                    sharing_neighbors = sum(1 for m in self._neighbors(aid) if m in sharers)
                    for channel, params in self._channels.items():
                        pressure = spread_pressure(
                            channel,
                            sharers_in_group=sharers_in_group,
                            group_size=max(1, len(contacts)),
                            global_share_ratio=global_ratio,
                            sharing_neighbors=sharing_neighbors,
                        )
                        rate = params.base_rate * self._mix[aid][channel] * pressure
                        if msg.kind == "correction":
                            rate *= params.correction_factor
                        if rate > 0 and self._rng.random() < rate:
                            self._expose(round_no, st, msg, channel)
                            break  # ได้ยินครั้งแรกจากช่องเดียวต่อ round
        return RunResult(
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            seed=self._seed,
            rounds=rounds,
            states=self._states,
            trail=tuple(self._trail),
        )
