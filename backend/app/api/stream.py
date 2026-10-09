"""
Stream 路由 — SSE 实时推流。

对齐 schema.md §8 与 PRD §6 实时共识/分歧。
MVP：通过 orchestrator.run_discussion 跑主持人单轮（开场→收尾），
所有 SSE 事件对齐前端 frontend/src/api/stream.js 的 handler。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Topic
from app.stream.runner import cancel_discussion, subscribe as subscribe_run

router = APIRouter(prefix="/topics/{topic_id}/stream", tags=["stream"])


def _get_topic_or_404(db: Session, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Topic {topic_id} not found"
        )
    return topic


@router.get("")
async def stream_discussion(
    topic_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """SSE：Transcript 流式 + 专家状态切换 + Insight 增量。

    MVP 阶段只跑主持人单轮（开场 → 收尾），阶段 4 后扩展为完整循环。
    事件类型（对齐 frontend/src/api/stream.js）：
      - transcript  : 发言增量
      - state       : 嘉宾状态切换 (idle/preparing/speaking)
      - insight     : 共识/分歧增量（MVP 不发）
      - system      : 系统消息
      - heartbeat   : 心跳保活
      - end         : 流结束
    """
    topic = _get_topic_or_404(db, topic_id)
    if topic.status not in ("ongoing", "summarizing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Topic status must be 'ongoing' or 'summarizing' to stream, got '{topic.status}'",
        )
    if not settings.is_llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM API Key not configured.",
        )

    async def event_generator():
        """订阅服务端单实例编排：多个连接共享同一场讨论。

        晚加入者会收到 history 补发；客户端断开仅退订，不影响讨论继续。
        """
        async for ev in subscribe_run(topic_id):
            yield ev

    return EventSourceResponse(event_generator())


@router.post("/cancel")
async def cancel_discussion_endpoint(topic_id: int, db: Session = Depends(get_db)):
    """强制中断一场正在运行的讨论。

    取消后台编排任务，并将 topic.status 置为 cancelled（终态）。
    已取消/已归档的讨论返回 400。
    """
    topic = _get_topic_or_404(db, topic_id)
    if topic.status not in ("ongoing", "summarizing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel topic in status '{topic.status}' (must be ongoing/summarizing)",
        )

    cancelled = await cancel_discussion(topic_id)

    # 更新 topic 状态为 cancelled（即使 session 已不存在也标记，防止状态机卡死）
    from datetime import datetime, timezone

    topic.status = "cancelled"
    topic.ended_at = datetime.now(timezone.utc).isoformat()
    topic.updated_at = datetime.now(timezone.utc).isoformat()
    if not topic.summary:
        topic.summary = "（讨论已被用户中断）"
    db.commit()

    return {
        "topic_id": topic_id,
        "cancelled": cancelled,
        "status": topic.status,
    }


@router.get("/replay")
def replay_discussion(
    topic_id: int,
    db: Session = Depends(get_db),
):
    """回放已归档讨论。

    PRD §4.1：首页可加入观察已有讨论；archived 可回放。
    返回按 turn_index 顺序的完整 transcript + 最终版 insight。
    """
    from sqlalchemy import select

    from app.models import Guest, Transcript
    from app.models import Insight

    topic = _get_topic_or_404(db, topic_id)
    if topic.status not in ("archived", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Replay requires archived/cancelled topic, got '{topic.status}'",
        )

    transcripts = (
        db.execute(
            select(Transcript)
            .where(Transcript.topic_id == topic_id)
            .order_by(Transcript.turn_index)
        )
        .scalars()
        .all()
    )
    guest_ids = {t.guest_id for t in transcripts}
    guests = (
        db.execute(select(Guest).where(Guest.id.in_(guest_ids))).scalars().all()
    )
    guest_map = {g.id: g for g in guests}

    transcript_payload = [
        {
            "id": t.id,
            "topic_id": t.topic_id,
            "guest_id": t.guest_id,
            "guest_name": guest_map[t.guest_id].name if t.guest_id in guest_map else "",
            "guest_color": guest_map[t.guest_id].color if t.guest_id in guest_map else "#888888",
            "turn_index": t.turn_index,
            "speech_type": t.speech_type,
            "status": t.status,
            "content": t.content,
        }
        for t in transcripts
    ]

    insights = (
        db.execute(
            select(Insight).where(Insight.topic_id == topic_id, Insight.is_final == 1)
        )
        .scalars()
        .all()
    )
    insight_payload = [
        {
            "id": i.id,
            "topic_id": i.topic_id,
            "type": i.type,
            "summary": i.summary,
            "strength": i.strength,
            "version": i.version,
            "is_final": bool(i.is_final),
            "created_at": i.created_at,
            "updated_at": i.updated_at,
        }
        for i in insights
    ]

    return {
        "topic_id": topic_id,
        "transcripts": transcript_payload,
        "insights": insight_payload,
    }
