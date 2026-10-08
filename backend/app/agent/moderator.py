"""
主持人 Agent — 开场白流式 + 收尾总结。

PRD §3.3：主持人在讨论开始与结束时发言。
MVP 阶段只跑主持人单轮（开场→收尾），阶段 4 加入专家抢答后再扩展。
"""

from __future__ import annotations

from typing import AsyncIterator

from app.agent.base import AgentContext
from app.llm import get_llm_client
from app.llm.prompts import opening_prompt, summary_prompt


class ModeratorAgent:
    """主持人 Agent。

    与 Agent 基类解耦——主持人有特殊职责（开场/收尾/追问），
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
        async for delta in client.chat_stream(messages, temperature=0.7, max_tokens=512):
            yield delta

    async def closing(self, ctx: AgentContext) -> AsyncIterator[str]:
        """流式输出收尾总结，基于已有发言。"""
        client = get_llm_client()
        messages = summary_prompt(ctx.topic_title, ctx.as_text())
        async for delta in client.chat_stream(messages, temperature=0.4, max_tokens=768):
            yield delta
