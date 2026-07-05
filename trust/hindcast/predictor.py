"""Hindcast predictor — agent ทำนาย prediction targets จากข้อมูลก่อน cutoff เท่านั้น

นี่คือหัวใจของ exit criteria Phase 0 ("hindcast ผ่าน ≥ 3/5 เหตุการณ์"):
crowd agent K ตัว (ใต้ hindcast prompt เดิมที่ผ่าน leak gate แล้ว) โหวตทิศทางของ claim
→ majority = คำทำนายของระบบ → เทียบ truth.yaml (ไฟล์ scorer เท่านั้น ห้ามเข้า prompt)

fail-closed: agent ตอบ parse ไม่ได้ = ไม่นับเสียง; ไม่มีเสียงเลย/เสมอกัน = ทำนายไม่ได้ = นับผิด
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from core.llm import LLMAdapter, ModelTier
from core.text import sanitize_llm_text
from trust.hindcast.loader import HindcastEvent
from trust.hindcast.prompt import build_hindcast_system_prompt, thai_date


@dataclass(frozen=True)
class AgentVote:
    answer: bool | None  # None = parse ไม่ได้
    confidence: float
    reason: str


@dataclass(frozen=True)
class TargetPrediction:
    target_id: str
    claim: str
    votes: tuple[AgentVote, ...]
    predicted: bool | None  # majority ของเสียงที่นับได้; None = ตัดสินไม่ได้
    truth: bool
    correct: bool  # predicted == truth (None = False เสมอ, fail-closed)

    @property
    def vote_split(self) -> str:
        yes = sum(1 for v in self.votes if v.answer is True)
        no = sum(1 for v in self.votes if v.answer is False)
        bad = sum(1 for v in self.votes if v.answer is None)
        return f"{yes}จริง/{no}ไม่จริง" + (f"/{bad}เสียงเสีย" if bad else "")


def build_prediction_prompt(claim: str, cutoff_th: str) -> str:
    return f"""คำถามคาดการณ์ (วันนี้คือ {cutoff_th} — เหตุการณ์ยังไม่เกิด):

"{claim}"

ชั่งน้ำหนักจากข้อมูลที่คุณอ่านมาทั้งหมด ณ วันนี้ แล้วประเมินว่าข้อความนี้จะกลายเป็นจริงหรือไม่
ห้ามอ้างว่ารู้ผล — นี่คือการคาดการณ์ล่วงหน้าเท่านั้น

ตอบเป็น JSON เท่านั้น: {{"answer": true หรือ false, "confidence": 0.0-1.0, "reason": "เหตุผลสั้นๆ"}}"""


def parse_vote(raw: str) -> AgentVote:
    text = sanitize_llm_text(raw)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data.get("answer"), bool):
                conf = float(data.get("confidence", 0.5))
                return AgentVote(
                    answer=data["answer"],
                    confidence=min(1.0, max(0.0, conf)),
                    reason=str(data.get("reason", ""))[:300],
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return AgentVote(answer=None, confidence=0.0, reason=f"parse ไม่ได้: {text[:120]}")


def majority(votes: list[AgentVote]) -> bool | None:
    yes = sum(1 for v in votes if v.answer is True)
    no = sum(1 for v in votes if v.answer is False)
    if yes == no:  # รวมกรณีไม่มีเสียงนับได้เลย
        return None
    return yes > no


def load_truth(event_dir: Path | str) -> dict[str, bool]:
    """ground truth สำหรับ scorer เท่านั้น — ห้ามส่งเข้า prompt ใดๆ"""
    return yaml.safe_load((Path(event_dir) / "truth.yaml").read_text(encoding="utf-8"))


def predict_event(
    adapter: LLMAdapter,
    event: HindcastEvent,
    truth: dict[str, bool],
    *,
    agents_per_target: int,
    seed: int,
    on_progress=None,
) -> list[TargetPrediction]:
    system_prompt = build_hindcast_system_prompt(event)
    cutoff_th = thai_date(event.cutoff_date)
    predictions: list[TargetPrediction] = []
    for target in event.prediction_targets:
        votes = []
        for i in range(agents_per_target):
            raw = adapter.chat(
                ModelTier.CROWD,
                [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": build_prediction_prompt(target["claim"], cutoff_th),
                    },
                ],
                max_tokens=300,
                seed=seed + i,  # กระจายมุมมองด้วย seed ต่างกัน
            ).text
            votes.append(parse_vote(raw))
        predicted = majority(votes)
        prediction = TargetPrediction(
            target_id=target["id"],
            claim=target["claim"],
            votes=tuple(votes),
            predicted=predicted,
            truth=truth[target["id"]],
            correct=(predicted is not None and predicted == truth[target["id"]]),
        )
        predictions.append(prediction)
        if on_progress:
            on_progress(prediction)
    return predictions


def event_passes(predictions: list[TargetPrediction]) -> bool:
    """เกณฑ์ต่อเหตุการณ์: ทำนายทิศถูกครบทุก target (เข้มไว้ก่อน — ดูเหตุผลในรายงาน)"""
    return all(p.correct for p in predictions)
