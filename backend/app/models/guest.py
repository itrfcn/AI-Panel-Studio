"""
Guest ORM 模型 — 嘉宾（主持人/专家角色）。

对齐 schema.md §3.2。
对应 PRD §4.2 阵容展示字段（姓名/职业/Title/立场/颜色）。
"""

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Guest(Base):
    """主持人或专家档案。"""

    __tablename__ = "guest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topic.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="moderator/expert"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="职业/Title")
    stance: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="立场")
    color: Mapped[str] = mapped_column(String(16), nullable=False, comment="专属颜色 hex")
    profile: Mapped[str | None] = mapped_column(Text, nullable=True, comment="详细档案 JSON")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    # --- relationships ---
    topic: Mapped["Topic"] = relationship(back_populates="guests")  # type: ignore[name-defined]  # noqa: F821
    transcripts: Mapped[list["Transcript"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="guest", cascade="all, delete-orphan"
    )
    event_points: Mapped[list["EventPoint"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="guest", foreign_keys="EventPoint.guest_id"
    )

    __table_args__ = (Index("idx_guest_topic_id", "topic_id", "sort_order"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Guest id={self.id} role={self.role} name={self.name!r}>"
