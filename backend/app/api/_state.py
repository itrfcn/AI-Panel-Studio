"""
状态机校验 helper — Topic.status 流转合法性。

对齐 schema.md §4.1 流转图：
  draft → setup → ongoing → summarizing → archived

允许同层回退（setup→draft 用于用户重新编辑阵容），
其他非法转换抛 ValueError，路由层包装为 400。
"""

from __future__ import annotations


# 流转邻接表：from -> {allowable to}
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"setup"},
    "setup": {"draft", "ongoing"},
    "ongoing": {"summarizing"},  # orchestrator 跑完后切 summarizing
    "summarizing": {"archived", "ongoing"},  # ongoing 容错：重跑收尾
    "archived": set(),  # 终态
}


def validate_transition(current: str, target: str) -> None:
    """校验 status 流转合法性。非法时抛 ValueError。"""
    if current == target:
        return  # 同态 no-op
    allowed = _TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Illegal topic status transition: {current!r} -> {target!r}. "
            f"Allowed: {sorted(allowed) or '(terminal state)'}"
        )


def is_terminal(status: str) -> bool:
    return status == "archived"
