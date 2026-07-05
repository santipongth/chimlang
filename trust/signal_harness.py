"""Out-of-Sample Harness (SIG-02) — พิสูจน์ว่า feature เพิ่ม predictive power จริงก่อนใช้

ตอบโจทย์ Backtest Illusion โดยตรง (ความเสี่ยงข้อ 2 ของ PRD):
- บังคับ train/test split ตามลำดับเวลา (ห้าม shuffle — กัน look-ahead leakage)
- วัดบน test set เท่านั้น: IC (Spearman rank correlation) + hit rate เทียบ baseline
  (baseline = ทายทิศทางข้างมากจาก train — naive แต่ยุติธรรม)
- ตัวอย่างเล็กเกิน = ปฏิเสธการสรุป (fail-closed: ไม่มีคำตอบ ดีกว่าคำตอบที่หลอกตัวเอง)
"""

import statistics
from dataclasses import dataclass

MIN_TEST_POINTS = 5


class SampleTooSmallError(ValueError):
    pass


def train_test_split_chrono(
    xs: list[float], ys: list[float], *, test_frac: float = 0.3
) -> tuple[list[float], list[float], list[float], list[float]]:
    """แบ่งตามลำดับเวลาเท่านั้น — test คือช่วงท้ายสุด (อนาคตเทียบ train เสมอ)"""
    if len(xs) != len(ys):
        raise ValueError("feature กับ target ต้องยาวเท่ากัน (จับคู่ตามเวลา)")
    n_test = max(1, round(len(xs) * test_frac))
    n_train = len(xs) - n_test
    if n_test < MIN_TEST_POINTS:
        raise SampleTooSmallError(
            f"test set มีแค่ {n_test} จุด (< {MIN_TEST_POINTS}) — เล็กเกินกว่าจะสรุป "
            "predictive power อย่างซื่อสัตย์"
        )
    return xs[:n_train], ys[:n_train], xs[n_train:], ys[n_train:]


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):  # เฉลี่ยอันดับเมื่อค่าเท่ากัน (tie)
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def information_coefficient(feature: list[float], target: list[float]) -> float:
    """Spearman rank IC — สหสัมพันธ์อันดับระหว่าง feature กับผลจริง"""
    if len(feature) < 2:
        return 0.0
    rx, ry = _ranks(feature), _ranks(target)
    sx, sy = statistics.pstdev(rx), statistics.pstdev(ry)
    if sx == 0 or sy == 0:
        return 0.0
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    cov = statistics.fmean([(a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)])
    return cov / (sx * sy)


def hit_rate(feature: list[float], target: list[float]) -> float:
    """สัดส่วนที่ทิศทาง feature (สูง/ต่ำเทียบ median) ตรงกับทิศทาง target

    ใช้ f >= median เป็นฝั่ง "สูง" — ถ้า feature แบนราบ (ทุกค่าเท่ากัน) จะทายขึ้นหมด
    ซึ่งถูกกรองโดยเงื่อนไข ic_test > 0 ใน improves_over_baseline อยู่แล้ว
    """
    med = statistics.median(feature)
    hits = sum(
        1
        for f, t in zip(feature, target, strict=True)
        if (f >= med and t > 0) or (f < med and t <= 0)
    )
    return hits / len(feature)


@dataclass(frozen=True)
class OOSReport:
    n_train: int
    n_test: int
    ic_test: float
    hit_rate_test: float
    baseline_hit_rate: float

    @property
    def improves_over_baseline(self) -> bool:
        return self.hit_rate_test > self.baseline_hit_rate and self.ic_test > 0

    def to_dict(self) -> dict:
        return {
            "n_train": self.n_train,
            "n_test": self.n_test,
            "ic_test": round(self.ic_test, 4),
            "hit_rate_test": round(self.hit_rate_test, 4),
            "baseline_hit_rate": round(self.baseline_hit_rate, 4),
            "improves_over_baseline": self.improves_over_baseline,
            "note": "วัดบน test set (ช่วงเวลาท้ายสุด) เท่านั้น — train/test split ตามเวลา ห้าม shuffle",
        }


def evaluate(feature_series: list[float], target_series: list[float]) -> OOSReport:
    """ประเมิน out-of-sample เต็มวงจร — คืนรายงานซื่อสัตย์ทั้งผ่านและไม่ผ่าน"""
    _x_train, y_train, x_test, y_test = train_test_split_chrono(feature_series, target_series)
    # baseline: ทายทิศข้างมากจาก train แล้ววัดบน test (naive persistence of direction)
    majority_up = sum(1 for y in y_train if y > 0) >= len(y_train) / 2
    baseline_hits = sum(1 for y in y_test if (y > 0) == majority_up)
    return OOSReport(
        n_train=len(y_train),
        n_test=len(y_test),
        ic_test=information_coefficient(x_test, y_test),
        hit_rate_test=hit_rate(x_test, y_test),
        baseline_hit_rate=baseline_hits / len(y_test),
    )
