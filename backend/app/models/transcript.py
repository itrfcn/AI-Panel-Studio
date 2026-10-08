"""
Transcript ORM 模型 — 实时发言流。

对齐 schema.md §3.3。
对应 PRD §4.3 Transcript 区，不记录"举手"等内部事件（内部事件入 EventPoint）。
"""

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transcript(Base):
    """一条发言记录。"""

    __tablename__ = "transcript"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic.id", ondelete="CASCADE"), nullable=False
    )
    guest_id: Mapped[int] = mapped_column(
        ForeignKey("guest.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="发言轮次序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="发言内容")
    speech_type: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="opening/followup/rebute/supplement/grab/summary",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
        comment="pending/streaming/done/aborted",
    )
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # --- relationships ---
    topic: Mapped["Topic"] = relationship(back_populates="transcripts")  # type: ignore[name-defined]  # noqa: F821
    guest: Mapped["Guest"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="transcripts", foreign_keys=[guest_id]
    )

    __table_args__ = (
        UniqueConstraint("topic_id", "turn_index", name="uq_transcript_topic_turn"),
        Index("idx_transcript_status", "status"),
        Index("idx_transcript_guest", "guest_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transcript id={self.id} turn={self.turn_index} type={self.speech_type}>"
