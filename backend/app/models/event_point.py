"""
EventPoint ORM 模型 — 内部事件点。

对齐 schema.md §3.4。
对应 PRD §5.3 抢答仲裁与 §6.2 抽取事件触发。
UI 不可见的内部事件均入此表，不混入 Transcript。
"""

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EventPoint(Base):
    """内部事件记录（举手/仲裁/抽取触发/收尾等）。"""

    __tablename__ = "event_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic.id", ondelete="CASCADE"), nullable=False
    )
    guest_id: Mapped[int | None] = mapped_column(
        ForeignKey("guest.id", ondelete="SET NULL"), nullable=True,
        comment="触发者，系统触发可空",
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="hand_raise/grab_arbitration/grab_result/moderator_intervene/consensus_extract_trigger/closing_trigger",
    )
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="关联 Transcript 轮次")
    payload: Mapped[str | None] = mapped_column(Text, nullable=True, comment="事件负载 JSON")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    # --- relationships ---
    topic: Mapped["Topic"] = relationship(back_populates="event_points")  # type: ignore[name-defined]  # noqa: F821
    guest: Mapped["Guest | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="event_points", foreign_keys=[guest_id]
    )

    __table_args__ = (
        Index("idx_event_topic_turn", "topic_id", "turn_index"),
        Index("idx_event_type", "event_type"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EventPoint id={self.id} type={self.event_type} turn={self.turn_index}>"
