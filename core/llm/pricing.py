"""ตารางราคา model — fail-closed: model ที่ไม่มีราคาในตารางจะรันไม่ได้

ราคาถูกอ่านจาก config/pricing.yaml (USD ต่อ 1M token) เพื่อให้ cost guard
คำนวณได้เสมอ การเดาราคา = ความเสี่ยงงบบานปลาย จึงห้าม fallback เป็นค่า default
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[2] / "config" / "pricing.yaml"


class UnknownModelPricingError(RuntimeError):
    def __init__(self, model: str):
        super().__init__(
            f"ไม่พบราคาของ model '{model}' ใน config/pricing.yaml — "
            "เพิ่มราคาก่อนรัน (fail-closed เพื่อกันงบบานปลาย)"
        )
        self.model = model


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_m: float
    output_usd_per_m: float


class PricingRegistry:
    def __init__(self, table: dict[str, ModelPricing]):
        self._table = dict(table)

    @classmethod
    def from_yaml(cls, path: Path | str = DEFAULT_PRICING_PATH) -> "PricingRegistry":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        table = {
            model: ModelPricing(
                input_usd_per_m=float(entry["input_usd_per_m"]),
                output_usd_per_m=float(entry["output_usd_per_m"]),
            )
            for model, entry in (raw.get("models") or {}).items()
        }
        return cls(table)

    def get(self, model: str) -> ModelPricing:
        try:
            return self._table[model]
        except KeyError:
            raise UnknownModelPricingError(model) from None

    def merged(self, extra: dict[str, dict] | None) -> "PricingRegistry":
        """รวมราคาที่ผู้ใช้กำหนดจากหน้าตั้งค่า (P6 — LLM ปรับเองได้) ทับ/เพิ่มจาก yaml

        fail-closed คงเดิม: model ที่ไม่อยู่ทั้งสองแหล่ง = รันไม่ได้
        """
        table = dict(self._table)
        for model, e in (extra or {}).items():
            table[model] = ModelPricing(
                input_usd_per_m=float(e["input_usd_per_m"]),
                output_usd_per_m=float(e["output_usd_per_m"]),
            )
        return PricingRegistry(table)

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        p = self.get(model)
        return (input_tokens * p.input_usd_per_m + output_tokens * p.output_usd_per_m) / 1_000_000
