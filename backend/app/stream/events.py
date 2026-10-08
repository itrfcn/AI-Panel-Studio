"""
SSE 事件工厂 — 严格对齐 frontend/src/api/stream.js 的 handler。

事件名（小写）：
  - transcript : 发言增量（streaming/done/aborted）
  - state      : 嘉宾状态切换（idle/preparing/speaking）
  - insight    : 共识/分歧增量（create/update/finalize）— MVP 不发，阶段 5 用
  - system     : 系统消息（开始/异常/提示）
  - heartbeat  : 心跳保活
  - end        : 流结束

每个 make_* 函数返回 sse-starlette 期望的 dict：{event, data}。
data 永远是 JSON 字符串（ensure_ascii=False）。
"""

from __future__ import annotations

import json
from typing import Any


def _dumps(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)


def make_system_event(topic_id: int, message: str, **extra: Any) -> dict[str, str]:
    payload: dict[str, Any] = {"topic_id": topic_id, "message": message}
    payload.update(extra)
    return {"event": "system", "data": _dumps(payload)}


def make_state_event(
    topic_id: int,
    guest_id: int,
    guest_name: str,
    guest_color: str,
    state: str,
    thought: str = "",
) -> dict[str, str]:
    """state ∈ idle/preparing/speaking。

    对齐前端 GuestPanel.vue 的 stateMeta：idle/preparing/speaking。
    """
    return {
        "event": "state",
        "data": _dumps(
            {
                "topic_id": topic_id,
                "guest_id": guest_id,
                "guest_name": guest_name,
                "guest_color": guest_color,
                "state": state,
                "thought": thought,
            }
        ),
    }


def make_transcript_event(
    topic_id: int,
    transcript_id: int,
    guest_id: int,
    guest_name: str,
    guest_color: str,
    turn_index: int,
    speech_type: str,
    status: str,
    delta: str = "",
    content: str = "",
    reason: str | None = None,
) -> dict[str, str]:
    """发言增量事件。

    status=streaming 时携带 delta（增量文本）；
    status=done 时携带 content（完整文本）；
    status=aborted 时携带 reason。
    """
    payload: dict[str, Any] = {
        "topic_id": topic_id,
        "transcript_id": transcript_id,
        "guest_id": guest_id,
        "guest_name": guest_name,
        "guest_color": guest_color,
        "turn_index": turn_index,
        "speech_type": speech_type,
        "status": status,
        "delta": delta,
        "content": content,
    }
    if reason:
        payload["reason"] = reason
    return {"event": "transcript", "data": _dumps(payload)}


def make_insight_event(
    topic_id: int,
    insight_id: int,
    action: str,
    type: str,
    summary: str,
    strength: str,
    version: int,
    is_final: bool,
) -> dict[str, str]:
    """共识/分歧增量事件。MVP 不发，阶段 5 用。"""
    return {
        "event": "insight",
        "data": _dumps(
            {
                "topic_id": topic_id,
                "insight_id": insight_id,
                "action": action,
                "type": type,
                "summary": summary,
                "strength": strength,
                "version": version,
                "is_final": is_final,
            }
        ),
    }


def make_heartbeat_event() -> dict[str, str]:
    return {"event": "heartbeat", "data": "{}"}


def make_end_event(topic_id: int, summary: str | None = None) -> dict[str, str]:
    payload: dict[str, Any] = {"topic_id": topic_id}
    if summary:
        payload["summary"] = summary
    return {"event": "end", "data": _dumps(payload)}
