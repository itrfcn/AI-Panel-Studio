"""
Arbiter — 主持人仲裁多专家举手信号。

PRD §5.3：仲裁规则
  - 优先级：rebute > supplement > grab
  - 同级按举手时间戳 FIFO（asyncio.gather 返回顺序近似时间戳）

仲裁过程不调 LLM（规则化决策），但需将 hand_raise/grab_arbitration/grab_result
写入 EventPoint 表（PRD §5.4：内部事件不入 Transcript）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.agent.expert import HandSignal
from app.database import SessionLocal
from app.models import EventPoint


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(
    topic_id: int,
    event_type: str,
    *,
    guest_id: int | None = None,
    turn_index: int | None = None,
    payload: dict | None = None,
) -> int:
    """写入一条 EventPoint 行，返回 id。

    event_type ∈ hand_raise / grab_arbitration / grab_result /
                 moderator_intervene / consensus_extract_trigger / closing_trigger
    """
    with SessionLocal() as db:
        ep = EventPoint(
            topic_id=topic_id,
            guest_id=guest_id,
            event_type=event_type,
            turn_index=turn_index,
            payload=json.dumps(payload, ensure_ascii=False) if payload else None,
            created_at=_now_iso(),
        )
        db.add(ep)
        db.commit()
        db.refresh(ep)
        return ep.id


class Arbiter:
    """主持人仲裁器。

    用法：
      arbiter = Arbiter(topic_id)
      winner = await arbiter.arbitrate(signals, turn_index)
      # winner: HandSignal 或 None（无人举手）
    """

    def __init__(self, topic_id: int) -> None:
        self.topic_id = topic_id

    async def arbitrate(
        self,
        signals: list[HandSignal],
        turn_index: int,
        max_speakers: int = 3,
    ) -> list[HandSignal]:
        """对一组举手信号仲裁，返回排序后的发言者列表（前 max_speakers 个）。

        所有举手的专家都有机会发言——发言意图由专家自身 decide_raise_hand
        决定，仲裁器只负责按优先级排序（rebute > supplement > grab），
        不人为干预谁该发言。
        - 同级按举手时间戳 FIFO（asyncio.gather 返回顺序近似时间戳）
        - 记录 hand_raise / grab_arbitration / grab_result 事件
        """
        if not signals:
            return []

        # 1. 记录每个 hand_raise
        for sig in signals:
            record_event(
                self.topic_id,
                "hand_raise",
                guest_id=sig.guest_id,
                turn_index=turn_index,
                payload={"priority": sig.priority, "thought": sig.thought},
            )

        # 2. 仲裁：按优先级降序，同级 FIFO
        weighted = list(enumerate(signals))
        weighted.sort(
            key=lambda pair: (
                -ExpertAgentPriority[pair[1].priority],
                pair[0],
            )
        )
        winners = [pair[1] for pair in weighted[:max_speakers]]

        # 3. 记录 grab_arbitration + grab_result
        record_event(
            self.topic_id,
            "grab_arbitration",
            guest_id=None,
            turn_index=turn_index,
            payload={
                "candidates": [
                    {
                        "guest_id": s.guest_id,
                        "name": s.name,
                        "priority": s.priority,
                    }
                    for s in signals
                ],
                "rule": "rebute > supplement > grab; FIFO within same priority",
            },
        )
        for w in winners:
            record_event(
                self.topic_id,
                "grab_result",
                guest_id=w.guest_id,
                turn_index=turn_index,
                payload={
                    "winner": w.name,
                    "priority": w.priority,
                },
            )
        return winners


# 优先级权重表（数值越大越优先）—与 ExpertAgent.PRIORITY_WEIGHT 保持一致
ExpertAgentPriority = {"rebute": 3, "supplement": 2, "grab": 1}
