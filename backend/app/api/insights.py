"""
Insights 路由 — 共识与分歧查询。

对齐 schema.md §8 与 PRD §6。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Insight, Topic
from app.schemas.insight import InsightOut, InsightWithLinksOut

router = APIRouter(prefix="/topics/{topic_id}/insights", tags=["insights"])


def _get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Topic {topic_id} not found"
        )
    return topic


@router.get("", response_model=list[InsightOut])
def list_insights(
    topic_id: int,
    type_filter: str | None = None,
    final_only: bool = False,
    db: Session = Depends(get_db),
) -> list[InsightOut]:
    """列出共识/分歧（可按 type 过滤、只取最终版）。"""
    _get_topic_or_404(db, topic_id)
    stmt = select(Insight).where(Insight.topic_id == topic_id)
    if type_filter:
        stmt = stmt.where(Insight.type == type_filter)
    if final_only:
        stmt = stmt.where(Insight.is_final == 1)
    stmt = stmt.order_by(Insight.updated_at)
    rows = db.execute(stmt).scalars().all()
    return [InsightOut.model_validate(r) for r in rows]


@router.get("/{insight_id}", response_model=InsightWithLinksOut)
def get_insight(topic_id: int, insight_id: int, db: Session = Depends(get_db)) -> InsightWithLinksOut:
    """单条 Insight 详情（含关联发言/发言人）。"""
    _get_topic_or_404(db, topic_id)
    insight = db.get(Insight, insight_id)
    if insight is None or insight.topic_id != topic_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found")
    guest_ids = [link.guest_id for link in insight.guest_links]
    transcript_ids = [link.transcript_id for link in insight.speech_links]
    out = InsightWithLinksOut.model_validate(insight)
    out.guest_ids = guest_ids
    out.transcript_ids = transcript_ids
    return out
