"""
Stream 路由 — SSE 实时推流。

对齐 schema.md §8 与 PRD §6 实时共识/分歧。
注意：本骨架仅返回占位心跳，真正的多 Agent 调度与抽取待 LLM 接入后实现。
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Topic

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

    事件类型（schema 见 TranscriptStream / InsightStream）：
      - transcript  : 发言增量
      - state       : 专家状态切换 (待机/准备/发言中) — PRD §5
      - insight     : 共识/分歧增量 (create/update/finalize) — PRD §6
      - heartbeat   : 心跳保活

    TODO（接入 LLM 后实现）：
      1. 校验 topic.status == ongoing，否则 400 提示先 /start
      2. 实例化主持人/专家 Agent
      3. 主循环：主持人开场 → 专家抢答循环 → 主持人收尾
      4. 每轮发言完成触发共识/分歧抽取 Agent
      5. 所有事件 SSE 推送
    """
    topic = _get_topic_or_404(db, topic_id)
    if topic.status != "ongoing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Topic status must be 'ongoing' to stream, got '{topic.status}'",
        )
    if not settings.is_llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM API Key not configured.",
        )

    async def event_generator():
        # 骨架占位：发心跳 + 未实现提示，便于前端联调
        yield {
            "event": "system",
            "data": json.dumps(
                {
                    "topic_id": topic_id,
                    "message": "stream skeleton: agent loop not implemented yet",
                },
                ensure_ascii=False,
            ),
        }
        # 心跳保活
        for _ in range(3):
            await asyncio.sleep(1)
            yield {"event": "heartbeat", "data": "{}"}
        yield {"event": "end", "data": "{}"}

    return EventSourceResponse(event_generator())


@router.get("/replay")
def replay_discussion(
    topic_id: int,
    db: Session = Depends(get_db),
):
    """回放已归档讨论。

    PRD §4.1：首页可加入观察已有讨论；archived 可回放。
    TODO: 按 turn_index 顺序返回完整 transcript + 最终版 insight。
    """
    topic = _get_topic_or_404(db, topic_id)
    if topic.status != "archived":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Replay requires archived topic, got '{topic.status}'",
        )
    # TODO: 组装回放 payload
    return {"topic_id": topic_id, "message": "replay payload TODO"}
