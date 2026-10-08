"""
Orchestrator — 主循环 async generator。

PRD §3.3 多 Agent 调度。
完整循环（阶段 4-5 解锁后）：
  1. system(discussion started, phase=opening)
  2. state(moderator idle→preparing→speaking)
  3. transcript(opening, streaming→done)  ← 主持人开场
  4. state(moderator speaking→idle)
  5. [循环 MAX_TURNS 次] 每轮：
     a. 各专家并发 decide_raise_hand（asyncio.gather 加速）
     b. Arbiter 仲裁 → 胜者发言（state 变化 + transcript streaming→done）
     c. 触发 ExtractorAgent 增量抽取（T1+，T0 跳过）→ SSE insight 事件
  6. state(moderator idle→preparing→speaking)
  7. transcript(summary, streaming→done)  ← 主持人收尾
  8. state(moderator speaking→idle)
  9. ExtractorAgent.finalize → SSE insight finalize 事件
 10. topic.status: ongoing → summarizing → archived；topic.summary 落库
 11. end(summary)

跨 yield 不持有 session：每个 DB 写入块内独立 SessionLocal()，commit 后立即 close。
客户端断开时 try/finally 把 in-flight transcript 状态置 aborted。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.agent import (
    Arbiter,
    ExpertAgent,
    ExtractorAgent,
    ModeratorAgent,
    build_context,
)
from app.config import settings
from app.database import SessionLocal
from app.models import Guest, Topic, Transcript
from app.stream.events import (
    make_end_event,
    make_state_event,
    make_system_event,
    make_transcript_event,
)


# ---------------------------------------------------------------------------
# DB helpers（跨 yield 安全，每块独立 session）
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _PseudoGuest:
    """fallback：DB 中找不到 Guest 时的占位对象（仅含 SSE 事件所需字段）。"""

    def __init__(self, *, id: int, name: str, color: str) -> None:
        self.id = id
        self.name = name
        self.color = color


def _load_topic_moderator(topic_id: int) -> tuple[Topic, Guest, int]:
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
        next_turn = (max_turn if max_turn is not None else -1) + 1

        db.expunge(topic)
        db.expunge(moderator)
        return topic, moderator, next_turn


def _load_experts(topic_id: int) -> list[Guest]:
    """加载所有专家（按 sort_order 升序）。"""
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(Guest)
                .where(Guest.topic_id == topic_id, Guest.role == "expert")
                .order_by(Guest.sort_order)
            )
            .scalars()
            .all()
        )
        for r in rows:
            db.expunge(r)
        return list(rows)


def _next_turn_index(topic_id: int) -> int:
    """取下一个可用 turn_index（max+1，注意 0 是合法值不能 or）。"""
    with SessionLocal() as db:
        max_turn = db.scalar(
            select(func.max(Transcript.turn_index)).where(Transcript.topic_id == topic_id)
        )
        return (max_turn if max_turn is not None else -1) + 1


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
        return t.id


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


# ---------------------------------------------------------------------------
# 通用发言流式 helper
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# 整段发言在"零产出"时的最大尝试次数（LLMClient 内层已对每次请求重试，
# 这一层兜底供应商持续过载，如 4 次请求全部返回过载错误帧）
_MAX_SPEECH_ATTEMPTS = 3


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

    完成后写库 + yield transcript(done, content)。
    - 零产出失败（上游过载重试耗尽等）：整段重试，最多 _MAX_SPEECH_ATTEMPTS 次
    - 已产出部分内容后失败：不重试（避免重复），标记 aborted
    - CancelledError：标记 aborted 并向上抛（应用关闭）
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_SPEECH_ATTEMPTS + 1):
        full_text = ""
        error: Exception | None = None
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
            _finalize_transcript_row(
                transcript_id, full_text, status="aborted", reason="client disconnected"
            )
            raise
        except Exception as exc:  # noqa: BLE001
            error = exc

        if error is None:
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
            return

        last_exc = error
        logger.warning(
            "speech failed (transcript=%s attempt=%d/%d produced=%d chars): %s",
            transcript_id, attempt, _MAX_SPEECH_ATTEMPTS, len(full_text), error,
        )
        if full_text:
            # 已有部分产出，重试会导致内容重复，放弃本段
            break
        if attempt < _MAX_SPEECH_ATTEMPTS:
            yield make_system_event(
                topic_id,
                f"{speech_type} 上游暂时不可用，正在重试（第 {attempt} 次）…",
            )
            await asyncio.sleep(1.5 * attempt)
            continue

    _finalize_transcript_row(
        transcript_id, "", status="aborted", reason=str(last_exc)
    )
    yield make_system_event(topic_id, f"{speech_type} aborted: {last_exc}")


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------


async def _run_expert_round(
    *,
    topic: Topic,
    turn_number: int,
    max_turns: int,
    next_turn_index_val: int,
    pending_extracts: list[asyncio.Task] | None = None,
    mod_agent: ModeratorAgent | None = None,
    moderator: _PseudoGuest | None = None,
) -> AsyncIterator[dict[str, str]]:
    """跑一轮专家抢答发言。

    流程：
      1. 所有专家并发 decide_raise_hand
      2. Arbiter 仲裁（写 EventPoint：hand_raise/grab_arbitration/grab_result）
      3. 胜者发言（state 切换 + transcript streaming→done）
      4. 其余专家回 idle
      5. 触发 ExtractorAgent 增量抽取
    """
    topic_id = topic.id
    experts = _load_experts(topic_id)
    if not experts:
        yield make_system_event(topic_id, "no experts to speak, skip round")
        return

    # 加载当前上下文（所有专家共享同一份）
    with SessionLocal() as db:
        ctx = build_context(db, topic_id, topic.title)

    # 1. 各专家并发决策举手
    agents = [
        ExpertAgent(
            guest_id=e.id,
            name=e.name,
            title=e.title,
            stance=e.stance or "",
            color=e.color,
        )
        for e in experts
    ]

    yield make_system_event(
        topic_id,
        f"turn {turn_number}/{max_turns}: experts deciding raise_hand",
        phase="expert_decide",
    )

    # 并发决策：每个专家独立 LLM 调用
    signals_raw = await asyncio.gather(
        *(agent.decide_raise_hand(ctx, turn_number, max_turns) for agent in agents),
        return_exceptions=True,
    )
    signals: list = []
    for sig in signals_raw:
        if isinstance(sig, Exception):
            continue
        if sig is not None:
            signals.append(sig)

    # 把所有举手专家的 thought 通过 state 事件广播（hand_raised 态）
    # 用户可见"谁举手了"，仲裁后败者回 idle，胜者依次 speaking
    sig_by_guest_id = {s.guest_id: s for s in signals}
    for agent in agents:
        sig = sig_by_guest_id.get(agent.guest_id)
        if sig is not None:
            yield make_state_event(
                topic_id,
                agent.guest_id,
                agent.name,
                agent.color,
                "hand_raised",
                thought=sig.thought,
            )
        else:
            yield make_state_event(
                topic_id,
                agent.guest_id,
                agent.name,
                agent.color,
                "idle",
                thought="",
            )

    # 2. 仲裁（所有举手者按优先级排序发言，不人为限制谁该发言）
    arbiter = Arbiter(topic_id)
    winners = await arbiter.arbitrate(
        signals,
        turn_index=next_turn_index_val,
        max_speakers=3,
    )

    if not winners:
        # 无人举手：所有专家回 idle，记录 moderator_intervene
        from app.agent.arbiter import record_event

        record_event(
            topic_id,
            "moderator_intervene",
            guest_id=None,
            turn_index=next_turn_index_val,
            payload={"reason": "no expert raised hand"},
        )
        yield make_system_event(
            topic_id,
            f"turn {turn_number}: no expert raised hand, skip",
            phase="no_speaker",
        )
        return

    winner_ids = {w.guest_id for w in winners}

    # 3. 败者先切回 idle
    for agent in agents:
        if agent.guest_id not in winner_ids:
            yield make_state_event(
                topic_id,
                agent.guest_id,
                agent.name,
                agent.color,
                "idle",
                thought="",
            )

    # 4. 胜者依次发言（第二个能看到第一个的发言，形成交锋）
    current_turn = next_turn_index_val
    for winner in winners:
        winner_agent = next(a for a in agents if a.guest_id == winner.guest_id)

        yield make_state_event(
            topic_id,
            winner.guest_id,
            winner_agent.name,
            winner_agent.color,
            "speaking",
            thought=winner.thought,
        )

        speech_type = winner.priority
        transcript_id = _create_transcript_row(
            topic_id, winner.guest_id, current_turn, speech_type
        )

        # 每位发言前重载上下文（保证能看到前一位的发言）
        with SessionLocal() as db:
            speak_ctx = build_context(db, topic_id, topic.title)
            winner_guest = db.get(Guest, winner.guest_id)
            if winner_guest is not None:
                db.expunge(winner_guest)
            else:
                winner_guest = _PseudoGuest(
                    id=winner.guest_id, name=winner.name, color=winner.color
                )

        async for ev in _stream_speech(
            topic_id=topic_id,
            transcript_id=transcript_id,
            guest=winner_guest,
            turn_index=current_turn,
            speech_type=speech_type,
            agent_method=lambda w=winner, wa=winner_agent, sc=speak_ctx: wa.speak(
                sc, priority=w.priority
            ),
        ):
            yield ev

        # 该胜者回 idle
        yield make_state_event(
            topic_id,
            winner.guest_id,
            winner_agent.name,
            winner_agent.color,
            "idle",
            thought="",
        )

        current_turn = _next_turn_index(topic_id)

    # 3.5 主持人串联/追问（看完本轮发言后引导下一轮方向）
    if mod_agent is not None and moderator is not None:
        yield make_state_event(
            topic_id, moderator.id, moderator.name, moderator.color, "speaking"
        )
        followup_turn = _next_turn_index(topic_id)
        followup_id = _create_transcript_row(
            topic_id, moderator.id, followup_turn, "followup"
        )
        with SessionLocal() as db:
            interject_ctx = build_context(db, topic_id, topic.title)
        async for ev in _stream_speech(
            topic_id=topic_id,
            transcript_id=followup_id,
            guest=moderator,
            turn_index=followup_turn,
            speech_type="followup",
            agent_method=lambda ma=mod_agent, ic=interject_ctx: ma.interject(ic),
        ):
            yield ev
        yield make_state_event(
            topic_id, moderator.id, moderator.name, moderator.color, "idle"
        )

    # 4. 触发抽取（T1+）— 后台并发，不阻塞下一轮决策
    # 计算已有发言条数（不含开场？包含？按 PRD §6.3：T1=第1位专家发言完成）
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count())
            .select_from(Transcript)
            .where(Transcript.topic_id == topic_id)
        ) or 0
    if count >= settings.EXTRACTION_MIN_TRANSCRIPTS:
        yield make_system_event(
            topic_id,
            f"turn {turn_number}: triggering extraction (transcripts={count})",
            phase="extract",
        )
        with SessionLocal() as db:
            extract_ctx = build_context(db, topic_id, topic.title)
        extractor = ExtractorAgent(topic_id)
        task = asyncio.create_task(extractor.extract_incremental(extract_ctx))
        if pending_extracts is not None:
            pending_extracts.append(task)


async def run_discussion(topic_id: int) -> AsyncIterator[dict[str, str]]:
    """完整主循环。

    yield SSE 事件 dict；调用方（stream.py 路由）用 EventSourceResponse 包装。
    """
    topic, moderator, next_turn = _load_topic_moderator(topic_id)
    mod_agent = ModeratorAgent(name=moderator.name, title=moderator.title, color=moderator.color)

    yield make_system_event(topic_id, "discussion started", phase="opening")

    # --- 1. 开场白 ---
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
        agent_method=lambda: mod_agent.opening(topic.title, topic.expert_count),
    ):
        yield ev

    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "idle")

    # --- 2. 专家抢答循环 ---
    max_turns = settings.MAX_TURNS
    pending_extracts: list[asyncio.Task] = []
    for turn_n in range(1, max_turns + 1):
        # 等上一轮抽取完成（如果还在跑），与本轮专家决策并发不冲突
        while pending_extracts:
            task = pending_extracts.pop(0)
            try:
                insight_events = await task
            except Exception as exc:  # noqa: BLE001
                yield make_system_event(topic_id, f"extraction failed: {exc}")
                insight_events = []
            for ev in insight_events:
                yield ev

        next_turn_val = _next_turn_index(topic_id)
        # 重新加载 topic（状态可能在外部变更）
        with SessionLocal() as db:
            fresh = db.get(Topic, topic_id)
            if fresh is None or fresh.status not in ("ongoing", "summarizing"):
                yield make_system_event(topic_id, f"topic status={fresh.status if fresh else 'gone'}, stop expert loop")
                break
            # 用 fresh topic 重新构造（detach）
            db.expunge(fresh)
            topic = fresh

        async for ev in _run_expert_round(
            topic=topic,
            turn_number=turn_n,
            max_turns=max_turns,
            next_turn_index_val=next_turn_val,
            pending_extracts=pending_extracts,
            mod_agent=mod_agent,
            moderator=moderator,
        ):
            yield ev

    # 收尾前等最后一批抽取完成
    while pending_extracts:
        task = pending_extracts.pop(0)
        try:
            insight_events = await task
        except Exception as exc:  # noqa: BLE001
            yield make_system_event(topic_id, f"extraction failed: {exc}")
            insight_events = []
        for ev in insight_events:
            yield ev

    # --- 3. 切换到 summarizing，准备收尾 ---
    _transition_topic_status(topic_id, "summarizing")
    # 记录收尾触发事件
    from app.agent.arbiter import record_event

    record_event(
        topic_id,
        "closing_trigger",
        guest_id=None,
        turn_index=None,
        payload={"reason": "max_turns reached or no more speakers"},
    )
    yield make_system_event(topic_id, "phase=summary", phase="summary")

    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "preparing")
    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "speaking")

    with SessionLocal() as db:
        ctx = build_context(db, topic_id, topic.title)

    summary_turn = _next_turn_index(topic_id)
    summary_id = _create_transcript_row(topic_id, moderator.id, summary_turn, "summary")
    async for ev in _stream_speech(
        topic_id=topic_id,
        transcript_id=summary_id,
        guest=moderator,
        turn_index=summary_turn,
        speech_type="summary",
        agent_method=lambda: mod_agent.closing(ctx),
    ):
        yield ev

    yield make_state_event(topic_id, moderator.id, moderator.name, moderator.color, "idle")

    # --- 4. Extractor finalize（Tf）---
    yield make_system_event(topic_id, "phase=finalize_insights", phase="finalize")
    with SessionLocal() as db:
        final_ctx = build_context(db, topic_id, topic.title)
    extractor = ExtractorAgent(topic_id)
    try:
        finalize_events = await extractor.finalize(final_ctx)
    except Exception as exc:  # noqa: BLE001
        yield make_system_event(topic_id, f"finalize failed: {exc}")
        finalize_events = []
    for ev in finalize_events:
        yield ev

    # --- 5. 归档：把 summary 文本同时写到 Topic.summary ---
    summary_text = ""
    with SessionLocal() as db:
        t = db.get(Transcript, summary_id)
        if t is not None:
            summary_text = t.content
    _transition_topic_status(topic_id, "archived", summary=summary_text)

    yield make_end_event(topic_id, summary=summary_text)
