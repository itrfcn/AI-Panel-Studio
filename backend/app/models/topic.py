"""
Topic ORM 模型 — 话题/讨论。

对齐 schema.md §3.1。
对应 PRD §3.2 阶段定义（status 5 态流转）。
"""

from datetime import datetime

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Topic(Base):
    """一场圆桌讨论。

    status 流转：draft → setup → ongoing → summarizing → archived
    """

    __tablename__ = "topic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, comment="讨论话题标题")
    expert_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, comment="专家人数 2-6"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", comment="draft/setup/ongoing/summarizing/archived"
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, comment="ISO8601")
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, comment="ISO8601")
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="主持人收尾总结 自然语言")

    # --- relationships ---
    guests: Mapped[list["Guest"]] = relationship(  # type: ignore[name-defined]
        back_populates="topic", cascade="all, delete-orphan", order_by="Guest.sort_order"
    )
    transcripts: Mapped[list["Transcript"]] = relationship(  # type: ignore[name-defined]
        back_populates="topic", cascade="all, delete-orphan", order_by="Transcript.turn_index"
    )
    event_points: Mapped[list["EventPoint"]] = relationship(  # type: ignore[name-defined]
        back_populates="topic", cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(  # type: ignore[name-defined]
        back_populates="topic", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_topic_status", "status"),
        Index("idx_topic_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Topic id={self.id} status={self.status} title={self.title!r}>"
