"""
Agent 基类与上下文构建 — PRD §3.3 多 Agent 调度。

build_context 只取最近 K 条 Transcript（settings.AGENT_CONTEXT_WINDOW_K），
避免长上下文幻觉。返回 AgentContext dataclass，含 messages 列表与原始 transcript 行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Guest, Transcript


@dataclass
class AgentContext:
    """一个 Agent 在发言前可见的上下文快照。"""

    topic_id: int
    topic_title: str
    # 最近 K 条 transcript（按 turn_index 升序）
    transcripts: list[Transcript] = field(default_factory=list)
    # 与 transcripts 一一对应的发言人 Guest
    guests_by_id: dict[int, Guest] = field(default_factory=dict)

    def as_text(self) -> str:
        """把 transcript 拼成 LLM 可读的纯文本上下文。"""
        if not self.transcripts:
            return "(暂无发言)"
        lines: list[str] = []
        for t in self.transcripts:
            g = self.guests_by_id.get(t.guest_id)
            if g is None:
                lines.append(f"[guest#{t.guest_id}]：{t.content}")
                continue
            if g.role == "moderator":
                if t.speech_type == "followup":
                    lines.append(f"[主持人追问]{g.name}：{t.content}")
                else:
                    lines.append(f"[主持人]{g.name}：{t.content}")
            else:
                # 标注专家立场，便于其他专家识别该反驳谁
                stance = f"（{g.stance}）" if g.stance else ""
                lines.append(f"[专家]{g.name}{stance}：{t.content}")
        return "\n".join(lines)


def build_context(db: Session, topic_id: int, topic_title: str, k: int | None = None) -> AgentContext:
    """取最近 K 条 Transcript + 对应 Guest，构造 AgentContext。"""
    limit = k or settings.AGENT_CONTEXT_WINDOW_K
    rows = (
        db.execute(
            select(Transcript)
            .where(Transcript.topic_id == topic_id)
            .order_by(Transcript.turn_index.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    # 反转为升序，方便拼接
    rows.reverse()

    guest_ids = {t.guest_id for t in rows}
    guests_by_id: dict[int, Guest] = {}
    if guest_ids:
        guests = (
            db.execute(select(Guest).where(Guest.id.in_(guest_ids)))
            .scalars()
            .all()
        )
        guests_by_id = {g.id: g for g in guests}

    return AgentContext(
        topic_id=topic_id,
        topic_title=topic_title,
        transcripts=rows,
        guests_by_id=guests_by_id,
    )


# 兼容旧名引用
Any  # noqa: F401  pylint: disable=pointless-statement
