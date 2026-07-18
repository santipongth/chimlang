"""Thai Social Fabric — ช่องทาง 4 แบบ พลวัตการแพร่ต่างกัน (FAB-01/05)

พารามิเตอร์ default อิงคุณลักษณะจาก PRD (ยังไม่ calibrate กับข้อมูลสำรวจจริง — FAB-05
ให้ค่า default จากสำรวจการใช้สื่อไทยเมื่อได้ข้อมูล):

- line_closed_group: แพร่ช้า (เห็นเฉพาะในกลุ่มตัวเอง) แต่ trust สูง และ "ข่าวแก้" เข้ายาก
- public_feed: แพร่เร็ว มี virality (แรงตามสัดส่วนคนแชร์) trust ปานกลาง
- algo_feed: non-network — แพลตฟอร์มดันตามกระแสรวม ไม่สนว่ารู้จักใคร
- offline_wom: จำกัดเพื่อนบ้าน/ชุมชน ช้า แต่ trust สูง
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelParams:
    base_rate: float  # โอกาสพื้นฐานที่ exposure จะเกิดต่อ round เมื่อมีแรงส่งเต็ม
    trust: float  # โอกาสเชื่อเมื่อได้ยินผ่านช่องทางนี้
    correction_factor: float  # ตัวคูณ base_rate สำหรับ "ข่าวแก้" (closed group เข้ายาก)
    network: str  # group | followers | global | neighbors


CHANNELS: dict[str, ChannelParams] = {
    "line_closed_group": ChannelParams(
        base_rate=0.25, trust=0.85, correction_factor=0.3, network="group"
    ),
    "public_feed": ChannelParams(
        base_rate=0.70, trust=0.50, correction_factor=1.0, network="followers"
    ),
    "algo_feed": ChannelParams(base_rate=0.55, trust=0.40, correction_factor=1.0, network="global"),
    "offline_wom": ChannelParams(
        base_rate=0.20, trust=0.80, correction_factor=0.6, network="neighbors"
    ),
}

# ---- ค่าคงที่กลไกการแพร่ (ADR-0022) ----
# สถานะ: ตัวเลขสังเคราะห์จากคุณลักษณะเชิงคุณภาพใน PRD — ยังไม่ calibrate กับข้อมูลสำรวจจริง
# scripts/calibrate_fabric.py วัด sensitivity ของแต่ละตัว เพื่อบอกว่าตัวไหนต้อง calibrate ก่อน
# เมื่อได้ข้อมูลจริง (FAB-05) — แก้ค่าที่นี่จุดเดียว ห้าม hardcode ซ้ำในไฟล์อื่น
VIRALITY_BOOST = 1.8  # public_feed: ตัวคูณ global share ratio (virality ไม่เชิงเส้น)
ALGO_TREND_THRESHOLD = 0.1  # algo_feed: กระแสรวมขั้นต่ำก่อน algorithm เริ่มดัน
NEIGHBOR_SATURATION = 2  # offline_wom: เพื่อนบ้านแชร์กี่คนถึงแรงเต็ม


def spread_pressure(
    channel: str,
    *,
    sharers_in_group: int,
    group_size: int,
    global_share_ratio: float,
    sharing_neighbors: int,
) -> float:
    """แรงส่งของช่องทาง ณ round หนึ่ง (0..1) — โครงข่ายต่างกันตามชนิดช่องทาง"""
    if group_size <= 0:
        group_ratio = 0.0
    else:
        group_ratio = sharers_in_group / group_size
    match CHANNELS[channel].network:
        case "group":
            return group_ratio  # เห็นเฉพาะคนในกลุ่ม LINE เดียวกัน
        case "followers":
            # virality: แรงตามสัดส่วนคนแชร์ทั้งระบบ + boost ไม่เชิงเส้นเมื่อเริ่มติดกระแส
            return min(1.0, global_share_ratio * VIRALITY_BOOST)
        case "global":
            # algorithm ดันตามกระแสรวม (non-network) — ต้องมีกระแสถึงระดับหนึ่งก่อน
            return global_share_ratio if global_share_ratio >= ALGO_TREND_THRESHOLD else 0.0
        case "neighbors":
            return min(1.0, sharing_neighbors / NEIGHBOR_SATURATION)
    return 0.0
