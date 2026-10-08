"""
主持人 Agent — 开场、串联追问、收尾总结。

PRD §3.3：主持人负责开场、追问、串联和总结。
每轮专家发言后，主持人根据本轮内容输出简短串联或追问，引导下一轮方向。
"""

from __future__ import annotations

from typing import AsyncIterator

from app.agent.base import AgentContext
from app.llm import get_llm_client
from app.llm.prompts import (
    followup_prompt,
    opening_prompt,
    should_continue_prompt,
    summary_prompt,
)


class ModeratorAgent:
    """主持人 Agent。

    与 Agent 基类解耦——主持人有特殊职责（开场/串联/收尾），
    独立成类更直观；专家 Agent 由阶段 4 在 agent/expert.py 实现。
    """

    def __init__(self, name: str, title: str, color: str = "#3B82F6") -> None:
        self.name = name
        self.title = title
        self.color = color

    async def opening(
        self,
        topic_title: str,
        expert_count: int,
    ) -> AsyncIterator[str]:
        """流式输出开场白，逐 delta yield。"""
        client = get_llm_client()
        messages = opening_prompt(topic_title, self.name, expert_count)
        async for delta in client.chat_stream(messages, temperature=0.7, max_tokens=384):
            yield delta

    async def interject(self, ctx: AgentContext) -> AsyncIterator[str]:
        """每轮专家发言后，流式输出串联/追问，引导下一轮方向。"""
        client = get_llm_client()
        messages = followup_prompt(ctx.topic_title, ctx.as_text())
        async for delta in client.chat_stream(messages, temperature=0.5, max_tokens=256):
            yield delta

    async def closing(self, ctx: AgentContext) -> AsyncIterator[str]:
        """流式输出收尾总结，基于已有发言。"""
        client = get_llm_client()
        messages = summary_prompt(ctx.topic_title, ctx.as_text())
        async for delta in client.chat_stream(messages, temperature=0.4, max_tokens=512):
            yield delta

    async def should_continue(
        self, ctx: AgentContext, turn_number: int, max_turns: int, stale_round: bool
    ) -> tuple[bool, str]:
        """判断讨论是否应继续。返回 (是否继续, 原因)。stale_round=上轮无新洞见。"""
        client = get_llm_client()
        messages = should_continue_prompt(
            ctx.topic_title, ctx.as_text(), turn_number, max_turns, stale_round
        )
        try:
            result = await client.chat_json(messages, temperature=0.3, max_tokens=128)
        except Exception:
            # 解析失败时：上轮已无新内容则收尾，否则继续
            if stale_round:
                return False, "上轮无新洞见，默认收尾"
            return True, "决策解析失败，默认继续"
        cont = bool(result.get("continue", True))
        reason = str(result.get("reason", ""))
        return cont, reason
