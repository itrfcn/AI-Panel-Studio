"""
Expert Agent — 单个专家的抢答决策与发言。

PRD §5.2 专家状态机：待机 → 准备 → 发言中 → 待机（循环）。
PRD §5.3 抢答仲裁：举手 priority ∈ {rebute, supplement, grab}，仲裁优先级 rebute > supplement > grab。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from app.agent.base import AgentContext
from app.llm import LLMJsonError, get_llm_client
from app.llm.prompts import expert_speak_prompt, raise_hand_prompt


@dataclass
class HandSignal:
    """一个专家的举手信号。"""

    guest_id: int
    name: str
    color: str
    stance: str
    title: str
    priority: str  # rebute / supplement / grab
    thought: str


class ExpertAgent:
    """单个专家 Agent。

    每轮：
      1. decide_raise_hand(ctx, turn_number) → HandSignal | None（不举手返回 None）
      2. speak(ctx, priority) → AsyncIterator[str] 流式发言
    """

    # 仲裁优先级权重（数值越大越优先发言）
    PRIORITY_WEIGHT = {"rebute": 3, "supplement": 2, "grab": 1}

    def __init__(
        self,
        guest_id: int,
        name: str,
        title: str,
        stance: str,
        color: str,
    ) -> None:
        self.guest_id = guest_id
        self.name = name
        self.title = title
        self.stance = stance or ""
        self.color = color

    async def decide_raise_hand(
        self,
        ctx: AgentContext,
        turn_number: int,
        max_turns: int,
    ) -> HandSignal | None:
        """决策是否举手。返回 HandSignal 或 None。"""
        client = get_llm_client()
        messages = raise_hand_prompt(
            expert_name=self.name,
            expert_stance=self.stance,
            expert_title=self.title,
            topic_title=ctx.topic_title,
            context_text=ctx.as_text(),
            turn_number=turn_number,
            max_turns=max_turns,
        )
        try:
            raw = await client.chat_json(messages, temperature=0.3)
        except LLMJsonError:
            # LLM 返回非 JSON 时保守不举手
            return None
        if not isinstance(raw, dict):
            return None
        if not raw.get("will_raise", False):
            return None
        priority = raw.get("priority", "grab")
        if priority not in self.PRIORITY_WEIGHT:
            priority = "grab"
        thought = (raw.get("thought") or "")[:60]
        return HandSignal(
            guest_id=self.guest_id,
            name=self.name,
            color=self.color,
            stance=self.stance,
            title=self.title,
            priority=priority,
            thought=thought,
        )

    async def speak(
        self,
        ctx: AgentContext,
        priority: str = "grab",
    ) -> AsyncIterator[str]:
        """流式输出本轮发言，逐 delta yield。"""
        client = get_llm_client()
        messages = expert_speak_prompt(
            expert_name=self.name,
            expert_stance=self.stance,
            expert_title=self.title,
            topic_title=ctx.topic_title,
            context_text=ctx.as_text(),
            priority=priority,
        )
        async for delta in client.chat_stream(messages, temperature=0.7):
            yield delta
