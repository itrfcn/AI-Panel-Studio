"""
单实例编排管理器（server-driven discussion）。

解决的问题：
- PRD §4.1 允许多个观察者随时加入同一场讨论；旧实现里每个 SSE 连接都会
  启动一个 run_discussion，导致同一 topic 并发双跑、turn_index 错位、
  客户端断开还会把整场讨论标记 aborted。

模型：
- 每个 topic 同一时刻只存在一个 _RunSession（一个后台 pump task）。
- 首个 SSE 连接启动 pump；后续连接只订阅，先补发 history（晚加入者可看到
  开场以来的全部事件），再接收实时事件。
- 单个订阅者断开仅退订，pump（讨论本身）继续直到归档。
- pump 结束（end/crash）后向所有订阅者发哨兵；session 随即注销，
  归档后的新连接由路由以 400 拒绝、前端转 /replay。

注意：单进程内有效（当前部署形态）。多进程部署需改为 Redis pub/sub。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.stream.events import make_end_event, make_system_event
from app.stream.orchestrator import run_discussion

# 订阅者队列上限：慢消费者（卡住的 SSE 连接）超过则被踢，不影响其他人
_QUEUE_MAX = 4096
_SENTINEL: dict = {"__sentinel__": "end"}


class _RunSession:
    """一场讨论的服务端运行态。"""

    def __init__(self, topic_id: int) -> None:
        self.topic_id = topic_id
        self.subscribers: set[asyncio.Queue] = set()
        self.history: list[dict] = []
        self.task: asyncio.Task | None = None


_sessions: dict[int, _RunSession] = {}
# 检查-创建 / pump 结束注销 与 订阅注册互斥，避免历史与实时事件重复或丢失
_guard = asyncio.Lock()


def _fanout(session: _RunSession, event: dict) -> None:
    """投递事件给所有订阅者（调用方须持有 _guard）。"""
    session.history.append(event)
    dead: list[asyncio.Queue] = []
    for q in tuple(session.subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    # 慢消费者：标记淘汰，稍后由其自身迭代发现哨兵退出
    for q in dead:
        session.subscribers.discard(q)
        try:
            q.put_nowait(_SENTINEL)
        except asyncio.QueueFull:
            pass


async def _pump(topic_id: int, session: _RunSession) -> None:
    """后台消费 run_discussion 并 fan-out。"""
    try:
        async for event in run_discussion(topic_id):
            async with _guard:
                _fanout(session, event)
    except asyncio.CancelledError:  # 应用关闭
        raise
    except Exception as exc:  # noqa: BLE001
        async with _guard:
            _fanout(session, make_system_event(topic_id, f"discussion crashed: {exc}"))
            _fanout(session, make_end_event(topic_id, summary=""))
    finally:
        async with _guard:
            for q in tuple(session.subscribers):
                try:
                    q.put_nowait(_SENTINEL)
                except asyncio.QueueFull:
                    # 满队列消费者直接丢弃，其队列读取终会因连接关闭结束
                    pass
            _sessions.pop(topic_id, None)


async def subscribe(topic_id: int) -> AsyncIterator[dict]:
    """订阅一场讨论（必要时启动编排），yield SSE 事件 dict。

    晚加入者先收 history 全量补发，再收实时事件。
    调用方（SSE 响应）关闭本生成器仅退订，不影响讨论进行。
    """
    async with _guard:
        session = _sessions.get(topic_id)
        if session is None:
            session = _RunSession(topic_id)
            _sessions[topic_id] = session
            session.task = asyncio.create_task(_pump(topic_id, session))
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        session.subscribers.add(queue)
        # 持锁快照：与 _pump 的 fanout 互斥，历史与实时不会重复/遗漏
        history_snapshot = list(session.history)

    try:
        for event in history_snapshot:
            yield event
        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            yield event
    finally:
        async with _guard:
            session.subscribers.discard(queue)


async def shutdown_all_sessions() -> None:
    """应用关闭：取消所有后台讨论任务。"""
    async with _guard:
        tasks = [s.task for s in _sessions.values() if s.task is not None]
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
