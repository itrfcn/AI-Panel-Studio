"""
Orchestrator — MVP 主循环 async generator。

PRD §3.3 多 Agent 调度。MVP 阶段只跑主持人单轮：
  1. system(discussion started)
  2. state(moderator idle→preparing→speaking)
  3. transcript(opening, streaming→done)
  4. state(moderator speaking→idle)
  5. topic.status: ongoing → summarizing
  6. state(moderator idle→preparing→speaking)
  7. transcript(summary, streaming→done)
  8. state(moderator speaking→idle)
  9. topic.status: summarizing → archived；topic.summary 落库
 10. end(summary)

阶段 4 加入专家抢答循环后再扩展（agent/expert.py + agent/arbiter.py）。

跨 yield 不持有 session：每个 DB 写入块内独立 SessionLocal()，commit 后立即 close。
客户端断开时 try/finally 把 in-flight transcript 状态置 aborted。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.agent import ModeratorAgent, build_context
from app.database import SessionLocal
from app.models import Guest, Topic, Transcript
from app.stream.events import (
    make_end_event,
    make_state_event,
    make_system_event,
    make_transcript_event,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_setup(topic_id: int) -> tuple[Topic, Guest, int]:
    """加载 topic + 主持人 + 已有最大 turn_index。"""
    with SessionLocal() as db:
        topic = db.get(Topic, topic_id)
        if topic is None:
            raise RuntimeError(f"Topic {topic_id} not found")
        if topic.status not in ("ongoing", "summarizing"):
            raise RuntimeError(
                f"Topic status must be ongoing/summarizing, got {topic.status!r}"
            )

        moderator = (
            db.execute(
                select(Guest).where(
                    Guest.topic_id == topic_id, Guest.role == "moderator"
                )
            )
            .scalars()
            .first()
        )
        if moderator is None:
            raise RuntimeError(f"Topic {topic_id} has no moderator")

        max_turn = db.scalar(
            select(func.max(Transcript.turn_index)).where(Transcript.topic_id == topic_id)
        )
        next_turn = (max_turn or -1) + 1

        # detach for use outside session
        db.expunge(topic)
        db.expunge(moderator)
        return topic, moderator, next_turn


def _create_transcript_row(
    topic_id: int,
    guest_id: int,
    turn_index: int,
    speech_type: str,
) -> int:
    """创建一条 streaming 态的 transcript 行，返回 id。"""
    with SessionLocal() as db:
        t = Transcript(
            topic_id=topic_id,
            guest_id=guest_id,
            turn_index=turn_index,
            content="",
            speech_type=speech_type,
            status="streaming",
            started_at=_now_iso(),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        transcript_id = t.id
        return transcript_id


def _finalize_transcript_row(
    transcript_id: int,
    content: str,
    status: str = "done",
    reason: str | None = None,
) -> None:
    """更新 transcript 行：status + content + completed_at。"""
    with SessionLocal() as db:
        t = db.get(Transcript, transcript_id)
        if t is None:
            return
        t.content = content
        t.status = status
        t.completed_at = _now_iso()
        # reason 不存表（schema 无该字段），仅作 SSE payload 用
        db.commit()


def _transition_topic_status(topic_id: int, new_status: str, summary: str | None = None) -> None:
    """切换 topic.status，可附带写入 summary。"""
    with SessionLocal() as db:
        topic = db.get(Topic, topic_id)
        if topic is None:
            return
        topic.status = new_status
        topic.updated_at = _now_iso()
        if new_status == "ongoing" and not topic.started_at:
            topic.started_at = _now_iso()
        if new_status == "archived" and not topic.ended_at:
            topic.ended_at = _now_iso()
        if summary is not None:
            topic.summary = summary
        db.commit()


async def _stream_speech(
    *,
    topic_id: int,
    transcript_id: int,
    guest: Guest,
    turn_index: int,
    speech_type: str,
    agent_method,
) -> AsyncIterator[dict[str, str]]:
    """通用：流式跑一段发言，期间 yield transcript(streaming, delta)。

    完成后调用方负责 finalize + yield transcript(done, content)。
    异常时标记 aborted 并 yield system 错误事件。
    """
    full_text = ""
    try:
        async for delta in agent_method():
            full_text += delta
            yield make_transcript_event(
                topic_id=topic_id,
                transcript_id=transcript_id,
                guest_id=guest.id,
                guest_name=guest.name,
                guest_color=guest.color,
                turn_index=turn_index,
                speech_type=speech_type,
                status="streaming",
                delta=delta,
            )
    except asyncio.CancelledError:
        # 客户端断开
        _finalize_transcript_row(transcript_id, full_text, status="aborted", reason="client disconnected")
        raise
    except Exception as exc:  # noqa: BLE001
        _finalize_transcript_row(transcript_id, full_text, status="aborted", reason=str(exc))
        yield make_system_event(topic_id, f"{speech_type} aborted: {exc}")
        return
    _finalize_transcript_row(transcript_id, full_text, status="done")
    yield make_transcript_event(
        topic_id=topic_id,
        transcript_id=transcript_id,
        guest_id=guest.id,
        guest_name=guest.name,
        guest_color=guest.color,
        turn_index=turn_index,
        speech_type=speech_type,
        status="done",
        content=full_text,
    )


async def run_discussion(topic_id: int) -> AsyncIterator[dict[str, str]]:
    """MVP 主循环。

    yield SSE 事件 dict；调用方（stream.py 路由）用 EventSourceResponse 包装。
    """
    topic, moderator, next_turn = _load_setup(topic_id)

    agent = ModeratorAgent(name=moderator.name, title=moderator.title, color=moderator.color)

    yield make_system_event(topic_id, "discussion started", phase="opening")

    # --- 开场白 ---
    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "preparing")
    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "speaking")

    opening_turn = next_turn
    opening_id = _create_transcript_row(topic_id, moderator.id, opening_turn, "opening")
    async for ev in _stream_speech(
        topic_id=topic_id,
        transcript_id=opening_id,
        guest=moderator,
        turn_index=opening_turn,
        speech_type="opening",
        agent_method=lambda: agent.opening(topic.title, topic.expert_count),
    ):
        yield ev

    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "idle")

    # --- 切换到 summarizing，准备收尾 ---
    _transition_topic_status(topic_id, "summarizing")
    yield make_system_event(topic_id, "phase=summary", phase="summary")

    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "preparing")
    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "speaking")

    # 重新加载上下文（开场白已落库）
    with SessionLocal() as db:
        ctx = build_context(db, topic_id, topic.title)

    summary_turn = opening_turn + 1
    summary_id = _create_transcript_row(topic_id, moderator.id, summary_turn, "summary")
    async for ev in _stream_speech(
        topic_id=topic_id,
        transcript_id=summary_id,
        guest=moderator,
        turn_index=summary_turn,
        speech_type="summary",
        agent_method=lambda: agent.closing(ctx),
    ):
        yield ev

    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "idle")

    # --- 归档：把 summary 文本同时写到 Topic.summary ---
    summary_text = ""
    with SessionLocal() as db:
        t = db.get(Transcript, summary_id)
        if t is not None:
            summary_text = t.content
    _transition_topic_status(topic_id, "archived", summary=summary_text)

    yield make_end_event(topic_id, summary=summary_text)
