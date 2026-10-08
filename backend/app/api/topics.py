"""
Topics 路由 — 讨论列表/创建/详情/状态流转/触发讨论。

对齐 schema.md §8 与 PRD §3 核心业务流程。
注意：本骨架暂不写大模型调用逻辑，仅落地数据持久化与状态流转。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Guest, Topic
from app.schemas.common import Page, PageParams
from app.schemas.guest import GuestOut
from app.schemas.topic import (
    TopicCreate,
    TopicDetailOut,
    TopicListOut,
    TopicUpdate,
)

router = APIRouter(prefix="/topics", tags=["topics"])


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic {topic_id} not found",
        )
    return topic


@router.get("", response_model=Page[TopicListOut])
def list_topics(
    params: PageParams = Depends(),
    status_filter: str | None = None,
    db: Session = Depends(get_db),
) -> Page[TopicListOut]:
    """首页：列出讨论（默认全部，可按 status 过滤）。

    PRD §4.1：展示当前所有正在进行的讨论列表。
    """
    stmt = select(Topic).order_by(Topic.updated_at.desc())
    if status_filter:
        stmt = stmt.where(Topic.status == status_filter)

    # MVP：用全量再切片，分页 count 不做窗口函数优化
    all_rows = db.execute(stmt).scalars().all()
    page_rows = all_rows[(params.page - 1) * params.page_size : params.page * params.page_size]

    items: list[TopicListOut] = []
    for t in page_rows:
        expert_role_count = (
            db.scalar(
                select(Guest).where(Guest.topic_id == t.id, Guest.role == "expert")
            )
            is not None
        )
        items.append(
            TopicListOut(
                id=t.id,
                title=t.title,
                expert_count=t.expert_count,
                status=t.status,  # type: ignore[arg-type]
                expert_role_count=int(expert_role_count),  # TODO: 用 count 改为人数
                has_summary=bool(t.summary),
                updated_at=t.updated_at,
            )
        )

    return Page[TopicListOut](
        items=items,
        total=len(all_rows),
        page=params.page,
        page_size=params.page_size,
    )


@router.post("", response_model=TopicDetailOut, status_code=status.HTTP_201_CREATED)
def create_topic(
    payload: TopicCreate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TopicDetailOut:
    """创建讨论（draft 态）。

    PRD §3.2：用户输入话题 + 专家人数后进入准备页。
    本端点只创建 draft 记录，不触发 LLM；阵容生成走 /roster/generate。
    """
    if not (settings.MIN_EXPERT_COUNT <= payload.expert_count <= settings.MAX_EXPERT_COUNT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"expert_count must be in [{settings.MIN_EXPERT_COUNT},{settings.MAX_EXPERT_COUNT}]",
        )

    now = _now_iso()
    topic = Topic(
        title=payload.title,
        expert_count=payload.expert_count,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)

    return TopicDetailOut.model_validate(topic)


@router.get("/{topic_id}", response_model=TopicDetailOut)
def get_topic(topic_id: int, db: Session = Depends(get_db)) -> TopicDetailOut:
    """讨论详情（含阵容）。"""
    topic = _get_topic_or_404(db, topic_id)
    guests = (
        db.execute(select(Guest).where(Guest.topic_id == topic_id).order_by(Guest.sort_order))
        .scalars()
        .all()
    )
    out = TopicDetailOut.model_validate(topic)
    out.guests = [GuestOut.model_validate(g) for g in guests]
    return out


@router.patch("/{topic_id}", response_model=TopicDetailOut)
def update_topic(
    topic_id: int,
    payload: TopicUpdate,
    db: Session = Depends(get_db),
) -> TopicDetailOut:
    """更新讨论状态/总结。

    状态流转约束（PRD §3.2 / schema.md §4.1）：
      draft → setup → ongoing → summarizing → archived
    """
    topic = _get_topic_or_404(db, topic_id)
    # TODO: 校验 status 流转合法性（非法转换 400）

    if payload.status is not None:
        topic.status = payload.status  # type: ignore[assignment]
        if payload.status == "ongoing" and not topic.started_at:
            topic.started_at = _now_iso()
        if payload.status == "archived" and not topic.ended_at:
            topic.ended_at = _now_iso()
    if payload.summary is not None:
        topic.summary = payload.summary

    topic.updated_at = _now_iso()
    db.commit()
    db.refresh(topic)
    return TopicDetailOut.model_validate(topic)


@router.post("/{topic_id}/start", response_model=TopicDetailOut)
def start_discussion(topic_id: int, db: Session = Depends(get_db)) -> TopicDetailOut:
    """触发讨论：阵容确认后调用，进入演播厅。

    PRD §3：阵容确认 → 启动演播厅。
    本端点只切换 status=ongoing；真正的多 Agent 调度在 stream 路由的 SSE 处理器中
    异步触发（TODO: 接入 LLM 客户端与 Agent 调度器）。
    """
    topic = _get_topic_or_404(db, topic_id)
    if topic.status != "setup":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Topic status must be 'setup' before start, got '{topic.status}'",
        )
    # 校验至少已确认 1 主持人 + N 专家
    guests = db.execute(select(Guest).where(Guest.topic_id == topic_id)).scalars().all()
    roles = {g.role for g in guests}
    if "moderator" not in roles or "expert" not in roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Roster not confirmed: moderator or experts missing",
        )

    topic.status = "ongoing"
    topic.started_at = _now_iso()
    topic.updated_at = _now_iso()
    db.commit()
    db.refresh(topic)
    return TopicDetailOut.model_validate(topic)
