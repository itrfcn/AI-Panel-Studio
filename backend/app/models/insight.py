"""
Insight ORM 模型族 — 共识与分歧及其关联。

对齐 schema.md §3.5–§3.8。
对应 PRD §6 共识/分歧生成时机与增量更新策略：
  - version 递增、不删除旧版本（PRD §6.5）
  - is_final 标记最终版
  - InsightSpeech/InsightGuest 落地"关联发言片段/关联发言人"
  - ReasoningChain 落地"推理链路"，由 event_point 推演
"""

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Insight(Base):
    """一条共识或分歧条目。"""

    __tablename__ = "insight"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="consensus/divergence"
    )
    summary: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="摘要 ≤30 字（应用层校验）"
    )
    strength: Mapped[str] = mapped_column(
        String(8), nullable=False, default="weak", comment="weak/medium/strong"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    is_final: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="0/1")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)

    # --- relationships ---
    topic: Mapped["Topic"] = relationship(back_populates="insights")  # type: ignore[name-defined]  # noqa: F821
    speech_links: Mapped[list["InsightSpeech"]] = relationship(  # type: ignore[name-defined]
        back_populates="insight", cascade="all, delete-orphan"
    )
    guest_links: Mapped[list["InsightGuest"]] = relationship(  # type: ignore[name-defined]
        back_populates="insight", cascade="all, delete-orphan"
    )
    reasoning_chain: Mapped[list["ReasoningChain"]] = relationship(  # type: ignore[name-defined]
        back_populates="insight", cascade="all, delete-orphan", order_by="ReasoningChain.step_index"
    )

    __table_args__ = (
        Index("idx_insight_topic", "topic_id", "type"),
        Index("idx_insight_updated", "topic_id", "updated_at"),
        Index("idx_insight_final", "topic_id", "is_final"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Insight id={self.id} type={self.type} v{self.version} final={self.is_final}>"


class InsightSpeech(Base):
    """Insight ↔ Transcript 多对多关联。"""

    __tablename__ = "insight_speech"

    insight_id: Mapped[int] = mapped_column(
        ForeignKey("insight.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    transcript_id: Mapped[int] = mapped_column(
        ForeignKey("transcript.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    relation: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="support/refute"
    )

    insight: Mapped["Insight"] = relationship(back_populates="speech_links")  # type: ignore[name-defined]
    transcript: Mapped["Transcript"] = relationship()  # type: ignore[name-defined]  # noqa: F821

    __table_args__ = (Index("idx_insight_speech_transcript", "transcript_id"),)


class InsightGuest(Base):
    """Insight ↔ Guest 多对多关联（涉及发言人）。"""

    __tablename__ = "insight_guest"

    insight_id: Mapped[int] = mapped_column(
        ForeignKey("insight.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    guest_id: Mapped[int] = mapped_column(
        ForeignKey("guest.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )

    insight: Mapped["Insight"] = relationship(back_populates="guest_links")  # type: ignore[name-defined]
    guest: Mapped["Guest"] = relationship()  # type: ignore[name-defined]  # noqa: F821


class ReasoningChain(Base):
    """推理链路：Insight 由哪些 event_point 推演而来。"""

    __tablename__ = "reasoning_chain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    insight_id: Mapped[int] = mapped_column(
        ForeignKey("insight.id", ondelete="CASCADE"), nullable=False
    )
    event_point_id: Mapped[int] = mapped_column(
        ForeignKey("event_point.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    insight: Mapped["Insight"] = relationship(back_populates="reasoning_chain")  # type: ignore[name-defined]
    event_point: Mapped["EventPoint"] = relationship()  # type: ignore[name-defined]  # noqa: F821

    __table_args__ = (
        UniqueConstraint("insight_id", "step_index", name="uq_reasoning_insight_step"),
        Index("idx_reasoning_insight", "insight_id", "step_index"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReasoningChain insight={self.insight_id} step={self.step_index}>"
