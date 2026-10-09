"""
Topic schemas — 讨论契约。

对齐 schema.md §3.1 与 PRD §3.2 阶段流转。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TopicStatus = Literal["draft", "setup", "ongoing", "summarizing", "archived", "cancelled"]


class TopicCreate(BaseModel):
    """创建讨论请求。"""

    title: str = Field(..., min_length=1, max_length=256, description="讨论话题标题")
    expert_count: int = Field(default=4, ge=2, le=6, description="专家人数 2-6")


class TopicUpdate(BaseModel):
    """更新讨论（仅允许部分字段）。"""

    status: TopicStatus | None = None
    summary: str | None = None


class TopicListOut(BaseModel):
    """首页讨论列表项。"""

    id: int
    title: str
    expert_count: int
    status: TopicStatus
    expert_role_count: int = Field(0, description="已确认专家人数（ongoing/archived 才有）")
    has_summary: bool = Field(False, description="是否已有收尾总结")
    updated_at: str

    model_config = {"from_attributes": True}


class TopicDetailOut(BaseModel):
    """讨论详情（含阵容）。"""

    id: int
    title: str
    expert_count: int
    status: TopicStatus
    created_at: str
    updated_at: str
    started_at: str | None = None
    ended_at: str | None = None
    summary: str | None = None
    guests: list["GuestOut"] = Field(default_factory=list)  # type: ignore[name-defined]  # noqa: F821

    model_config = {"from_attributes": True}


# 避免循环导入，延迟解析
from app.schemas.guest import GuestOut  # noqa: E402  pylint: disable=wrong-import-position
TopicDetailOut.model_rebuild()
