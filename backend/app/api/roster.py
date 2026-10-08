"""
Roster 路由 — 阵容生成与确认。

对齐 PRD §4.2 准备页与 schema.md §3.2。
注意：阵容生成需调用 LLM，本骨架暂留 TODO，先返回 501 占位，
待 LLM 客户端与 Prompt 工程模块就绪后接入。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Guest, Topic
from app.schemas.guest import GuestCreate, GuestOut, RosterGenerateRequest, RosterOut

router = APIRouter(prefix="/topics/{topic_id}/roster", tags=["roster"])


def _get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Topic {topic_id} not found"
        )
    return topic


@router.post("/generate", response_model=RosterOut)
def generate_roster(
    topic_id: int,
    payload: RosterGenerateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RosterOut:
    """生成候选阵容（主持人 + N 专家）。

    TODO（接入 LLM 后实现）：
      1. 校验 settings.is_llm_configured()，否则 503
      2. 构造 Prompt：话题 + 人数 + 立场多样性约束
      3. 调用 LLM 输出 JSON：[{role,name,title,stance,color,profile}]
      4. 写入 guest 表（status 仍为 setup 的候选态）
      5. 返回 RosterOut（is_confirmed=False）
    """
    if not settings.is_llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM API Key not configured. Set LLM_API_KEY in .env.",
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Roster generation pending LLM integration (skeleton only).",
    )


@router.get("", response_model=RosterOut)
def get_roster(topic_id: int, db: Session = Depends(get_db)) -> RosterOut:
    """获取当前已生成的阵容（候选或已确认）。"""
    _get_topic_or_404(db, topic_id)
    guests = (
        db.execute(
            select(Guest).where(Guest.topic_id == topic_id).order_by(Guest.sort_order)
        )
        .scalars()
        .all()
    )
    topic = db.get(Topic, topic_id)
    return RosterOut(
        topic_id=topic_id,
        guests=[GuestOut.model_validate(g) for g in guests],
        is_confirmed=(topic.status not in ("draft", "setup")) and bool(guests),
    )


@router.post("/confirm", response_model=RosterOut)
def confirm_roster(
    topic_id: int,
    db: Session = Depends(get_db),
) -> RosterOut:
    """用户确认阵容 → 进入可启动演播厅的 setup 状态。

    PRD §3：用户确认阵容后进入演播厅。
    本端点：
      - 校验已存在 1 moderator + N expert
      - 将 topic.status 切到 setup（待 /start 端点切 ongoing）
    """
    from datetime import datetime, timezone

    topic = _get_topic_or_404(db, topic_id)
    guests = (
        db.execute(
            select(Guest).where(Guest.topic_id == topic_id).order_by(Guest.sort_order)
        )
        .scalars()
        .all()
    )
    moderators = [g for g in guests if g.role == "moderator"]
    experts = [g for g in guests if g.role == "expert"]

    if len(moderators) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exactly 1 moderator required, got {len(moderators)}",
        )
    if len(experts) != topic.expert_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected {topic.expert_count} experts, got {len(experts)}",
        )

    topic.status = "setup"
    topic.updated_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    db.refresh(topic)

    return RosterOut(
        topic_id=topic_id,
        guests=[GuestOut.model_validate(g) for g in guests],
        is_confirmed=True,
    )
