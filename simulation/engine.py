"""Simulation engine v1 (SIM-03 ระดับกลไกการแพร่) — round-based, deterministic ต่อ seed

ขอบเขต v1 (M3): พลวัตการแพร่/เชื่อ/แชร์ของข้อความผ่าน 4 ช่องทาง + reasoning trail
เชิงเหตุการณ์ครบทุก agent — ชั้น "agent เขียนโพสต์เอง" (LLM) อยู่ใน voice.py แยกต่างหาก
เพื่อคุมต้นทุน (ADR-0002)

พฤติกรรมเชิงวัฒนธรรม (FAB-02):
- เกรงใจ + say-do gap: ความเชื่อส่วนตัว (believed) กับการแสดงออก (shared) แยกกัน —
  agent เกรงใจสูงจะเชื่อแต่ไม่แชร์ในที่สาธารณะ แต่กล้าส่งต่อในกลุ่มปิดมากกว่า
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from random import Random

from simulation.channels import CHANNELS, spread_pressure
from simulation.persona import Persona

GROUP_SIZE = 4  # ขนาดกลุ่ม LINE ต่อกลุ่ม (แบ่งตาม segment)

# ---- ค่าคงที่พฤติกรรมวัฒนธรรม (FAB-02) — สังเคราะห์ รอ calibrate (ADR-0022) ----
SAY_DO_CLOSED_BOOST = 0.4  # say-do gap เพิ่มโอกาสส่งต่อในกลุ่มปิด
KRENG_JAI_PUBLIC_SUPPRESS = 0.5  # เกรงใจกดการแชร์สาธารณะ
KRENG_JAI_CORRECTION_SUPPRESS = 0.5  # เกรงใจลดการเชื่อข่าวแก้ในกลุ่มปิด (เกรงใจผู้ส่งเดิม)

# ---- Re-exposure / complex contagion (ADR-0022) ----
# ของจริง: คนที่ได้ยินแล้วยังไม่เชื่อ ถูกโน้มน้าวซ้ำได้เมื่อแรงกดดันรอบข้างสูงขึ้น —
# engine v1 ตัดสินครั้งเดียวตลอดชีพซึ่งกดการแพร่แบบ complex contagion หายทั้งชั้น
# ทำแบบ conservative: โอกาสพิจารณาใหม่ลดลงครึ่งหนึ่งทุกครั้ง และไม่เกิน 3 ครั้ง/ข้อความ
RECONSIDER_MAX = 3
RECONSIDER_DECAY = 0.5

# ---- Common random numbers (ADR-0022) ----
# เดิม engine ใช้ RNG เส้นเดียวทั้งระบบ: การ inject ข้อความที่สองเปลี่ยนลำดับ draw ของ
# ข้อความแรกด้วย → คู่เทียบ A/B seed เดียวกัน (SIM-04 fork, compare, red team) ปน RNG noise
# ที่ไม่ใช่ผลเชิงสาเหตุ (calibration harness จับได้: delta คำชี้แจงพลิกเป็นบวก)
# แก้ด้วย hashed uniform ต่อ (seed, เหตุการณ์, msg, agent, ...) — draw อิสระต่อกันโดยสิ้นเชิง
# จึงเป็น common random numbers: ตัวแปรที่ไม่เกี่ยวกับ intervention ได้ draw เดิมทุก variant


def _hashed_uniform(seed: int, *key) -> float:
    digest = hashlib.blake2b(repr((seed, *key)).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


@dataclass(frozen=True)
class Message:
    msg_id: str
    kind: str  # rumor | correction
    text: str
    start_round: int
    seed_channel: str  # ช่องทางที่ข้อความถูกปล่อยครั้งแรก
    counters: str | None = None  # msg_id ของข่าวที่ข้อความนี้หักล้าง (belief revision)
    # broadcast_share > 0 = ปล่อยแบบสื่อมวลชน (แถลงข่าว/ข่าวทีวี) ถึงสัดส่วนนี้ของประชากรทันที
    # ที่ start_round — จำเป็นที่ scale ใหญ่: คำชี้แจงทางการไม่ได้ไหลจากคนเดียว (calibration 6 ก.ค. 2026)
    broadcast_share: float = 0.0


@dataclass
class AgentState:
    persona: Persona
    heard: dict[str, int] = field(default_factory=dict)  # msg_id -> round แรกที่ได้ยิน
    heard_via: dict[str, str] = field(default_factory=dict)  # msg_id -> channel แรก
    believed: dict[str, bool] = field(default_factory=dict)
    sharing: dict[str, bool] = field(default_factory=dict)  # ยังแชร์ต่ออยู่ไหม
    mutated: set[str] = field(default_factory=set)  # msg ที่ได้รับมาแบบเพี้ยน (FAB-04)
    reconsidered: dict[str, int] = field(default_factory=dict)  # msg_id -> ครั้งที่ถูกโน้มน้าวซ้ำ


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

    def expressors(self) -> set[str]:
        """agent ที่แชร์/แสดงออกอย่างน้อยหนึ่งข้อความ (TRUST-07: ผู้แสดงออก)"""
        return {aid for aid, st in self.states.items() if any(st.sharing.values())}

    def observers(self) -> set[str]:
        """agent ที่ได้ยินอย่างน้อยหนึ่งข้อความแต่ไม่เคยแชร์เลย (TRUST-07: ผู้สังเกตการณ์)

        กลุ่มนี้คือ silent majority — มีความเชื่อ/พฤติกรรมจริงแต่ไม่มีเสียงบนช่องทางสื่อสาร
        """
        return {aid for aid, st in self.states.items() if st.heard and not any(st.sharing.values())}

    def mutation_share(self, msg_id: str) -> float:
        """สัดส่วนผู้ได้ยินที่ได้รับเวอร์ชันเพี้ยน (FAB-04)"""
        heard = [st for st in self.states.values() if msg_id in st.heard]
        if not heard:
            return 0.0
        return sum(1 for st in heard if msg_id in st.mutated) / len(heard)

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
        rumor_mutation_rate: float = 0.0,
    ):
        """enabled_channels: จำกัดช่องทาง (ใช้ทำ isolated-channel benchmark) — None = ครบ 4

        rumor_mutation_rate (FAB-04): โอกาสที่ข่าวลือ "เพี้ยน" ระหว่างส่งต่อใน closed group
        (0-1, default 0 = ปิด) — ผู้รับเวอร์ชันเพี้ยนถูก mark + log ใน trail
        """
        if not 0.0 <= rumor_mutation_rate <= 1.0:
            raise ValueError("rumor_mutation_rate ต้องอยู่ในช่วง 0-1")
        self._mutation_rate = rumor_mutation_rate
        self._seed = seed
        self._states = {p.agent_id: AgentState(persona=p) for p in personas}
        self._order = sorted(self._states)  # ลำดับ deterministic
        self._index = {aid: i for i, aid in enumerate(self._order)}
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
        # เครือข่าย offline word-of-mouth (ADR-0022): ring แบบสุ่ม seeded แทนการใช้ลำดับ
        # agent_id ที่ sort แล้ว — ของเดิมเป็น artifact (เพื่อนบ้าน = id ติดกัน จึงเกาะ segment
        # เดียวกันเป็นสายยาว); ไม่มีข้อมูลภูมิศาสตร์จริงจึงใช้ ring สุ่มที่ผสมข้าม segment
        wom_order = list(self._order)
        Random(seed ^ 0x0FF11E).shuffle(wom_order)
        self._wom_neighbors: dict[str, tuple[str, ...]] = {}
        n_agents = len(wom_order)
        for i, aid in enumerate(wom_order):
            if n_agents <= 1:
                self._wom_neighbors[aid] = ()
            else:
                self._wom_neighbors[aid] = (
                    wom_order[(i - 1) % n_agents],
                    wom_order[(i + 1) % n_agents],
                )

    def inject(self, message: Message) -> None:
        self._messages.append(message)

    def preseed(self, message: Message, believer_ids: set[str]) -> None:
        """sync สถานะเริ่มต้นกับโลกจริง (war room REH-04): agent ที่ระบุเชื่อข้อความนี้แล้ว

        ใช้ start_round=0 — run() จะไม่ปล่อยข้อความซ้ำ (loop เริ่ม round 1) แต่แพร่ต่อ
        จากผู้แชร์ที่ preseed ไว้; การแชร์ของผู้เชื่อสุ่มตาม voice_activity (deterministic ต่อ seed)
        """
        if message.start_round != 0:
            raise ValueError("preseed ต้องใช้ message ที่ start_round=0 (กันปล่อยซ้ำใน run)")
        self._messages.append(message)
        for aid in sorted(believer_ids):
            st = self._states[aid]
            st.heard[message.msg_id] = 0
            st.heard_via[message.msg_id] = message.seed_channel
            st.believed[message.msg_id] = True
            st.sharing[message.msg_id] = (
                _hashed_uniform(self._seed, "preshare", message.msg_id, aid)
                < st.persona.voice_activity
            )
            self._log(0, aid, message, message.seed_channel, "preseeded")

    def _neighbors(self, agent_id: str) -> tuple[str, ...]:
        return self._wom_neighbors[agent_id]

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
        if (
            msg.kind == "rumor"
            and channel == "line_closed_group"
            and _hashed_uniform(self._seed, "mut", msg.msg_id, st.persona.agent_id)
            < self._mutation_rate
        ):
            # FAB-04: ข่าวลือเพี้ยนระหว่างส่งต่อในกลุ่มปิด (ตรวจสอบ/แก้ยากที่สุด)
            st.mutated.add(msg.msg_id)
            self._log(round_no, st.persona.agent_id, msg, channel, "heard_mutated")
        self._belief_draw(round_no, st, msg, channel, attempt=0)

    def _belief_draw(
        self, round_no: int, st: AgentState, msg: Message, channel: str, *, attempt: int
    ) -> None:
        """ตัดสินเชื่อ/แชร์ — ใช้ทั้งการได้ยินครั้งแรก (attempt=0) และการโน้มน้าวซ้ำ (1..3)"""
        p = st.persona
        believe_prob = CHANNELS[channel].trust
        if msg.kind == "correction" and channel == "line_closed_group":
            # ข่าวแก้ในกลุ่มปิดถูกลดทอนด้วยความเกรงใจผู้ส่งเดิม (corpus 2026-06-08)
            believe_prob *= 1.0 - KRENG_JAI_CORRECTION_SUPPRESS * p.kreng_jai
        if msg.kind == "correction":
            # P5-M4: adversarial agent ต้านคำชี้แจงทางการ (default 1.0 = เดิมเป๊ะ)
            believe_prob *= p.correction_receptivity
        believed = (
            _hashed_uniform(self._seed, "bel", msg.msg_id, p.agent_id, attempt) < believe_prob
        )
        st.believed[msg.msg_id] = believed
        if believed:
            self._log(round_no, p.agent_id, msg, channel, "believed")
            if msg.counters and st.believed.get(msg.counters):
                # belief revision: เชื่อข่าวหักล้าง → เลิกเชื่อ+เลิกแชร์ข่าวเดิม
                st.believed[msg.counters] = False
                st.sharing[msg.counters] = False
                self._log(round_no, p.agent_id, msg, channel, f"revised:{msg.counters}")
            share_prob = p.voice_activity
            if channel == "line_closed_group":
                # เกรงใจกดการแสดงออกสาธารณะ แต่ในกลุ่มปิดกล้าส่งต่อมากขึ้น (say-do gap)
                share_prob = min(1.0, share_prob + SAY_DO_CLOSED_BOOST * p.say_do_gap)
            else:
                share_prob *= 1.0 - KRENG_JAI_PUBLIC_SUPPRESS * p.kreng_jai
            if _hashed_uniform(self._seed, "share", msg.msg_id, p.agent_id, attempt) < share_prob:
                st.sharing[msg.msg_id] = True
                self._log(round_no, p.agent_id, msg, channel, "shared")

    def run(self, rounds: int) -> RunResult:
        n = len(self._states)
        for round_no in range(1, rounds + 1):
            for msg in self._messages:
                if round_no < msg.start_round:
                    continue
                if round_no == msg.start_round:
                    if msg.broadcast_share > 0:
                        # โหมดสื่อมวลชน: ถึงสัดส่วนประชากรทันที — RNG แยกต่อข้อความ
                        # (common random numbers: ไม่กวน draw ของข้อความอื่น)
                        k = max(1, round(msg.broadcast_share * n))
                        reached = Random(f"{self._seed}:bcast:{msg.msg_id}").sample(self._order, k)
                        for aid in sorted(reached):
                            self._expose(round_no, self._states[aid], msg, msg.seed_channel)
                        continue
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
                    # log แยกจาก "shared" (ที่มาจาก draw) — จำเป็นต่อ influence graph (SIM-09)
                    self._log(round_no, seeder, msg, msg.seed_channel, "seeded")
                    continue

                sharers = {a for a in self._order if self._states[a].sharing.get(msg.msg_id)}
                global_ratio = len(sharers) / n
                for aid in self._order:
                    st = self._states[aid]
                    already_heard = msg.msg_id in st.heard
                    if already_heard and (
                        st.believed.get(msg.msg_id)
                        or st.reconsidered.get(msg.msg_id, 0) >= RECONSIDER_MAX
                    ):
                        # เชื่อแล้ว หรือถูกโน้มน้าวซ้ำครบโควตา — จบสำหรับข้อความนี้
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
                        if already_heard:
                            # re-exposure (ADR-0022): ได้ยินแล้วแต่ยังไม่เชื่อ — โอกาสพิจารณา
                            # ใหม่ลดครึ่งหนึ่งต่อครั้ง (complex contagion แบบ conservative)
                            rate *= RECONSIDER_DECAY ** (st.reconsidered.get(msg.msg_id, 0) + 1)
                        draw = _hashed_uniform(
                            self._seed, "exp", msg.msg_id, aid, round_no, channel
                        )
                        if rate > 0 and draw < rate:
                            if already_heard:
                                attempt = st.reconsidered.get(msg.msg_id, 0) + 1
                                st.reconsidered[msg.msg_id] = attempt
                                self._log(round_no, aid, msg, channel, "reexposed")
                                self._belief_draw(round_no, st, msg, channel, attempt=attempt)
                            else:
                                self._expose(round_no, st, msg, channel)
                            break  # ช่องเดียวต่อ round ต่อข้อความ
        return RunResult(
            run_id=f"run-{uuid.uuid4().hex[:8]}",
            seed=self._seed,
            rounds=rounds,
            states=self._states,
            trail=tuple(self._trail),
        )
