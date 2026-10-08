"""
Guest schemas — 嘉宾契约（主持人/专家）。

对齐 schema.md §3.2 与 PRD §4.2 阵容展示。
"""

from typing import Literal

from pydantic import BaseModel, Field

GuestRole = Literal["moderator", "expert"]


class GuestCreate(BaseModel):
    """嘉宾创建请求（由阵容生成 Agent 输出，前端可查看后确认）。"""

    role: GuestRole
    name: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=128, description="职业/Title")
    stance: str | None = Field(None, max_length=256)
    color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$", description="hex 颜色 #RRGGBB")
    profile: str | None = Field(None, description="详细档案 JSON 字符串")
    sort_order: int = Field(0, ge=0)


class GuestOut(BaseModel):
    """嘉宾响应。"""

    id: int
    topic_id: int
    role: GuestRole
    name: str
    title: str
    stance: str | None = None
    color: str
    profile: str | None = None
    sort_order: int
    created_at: str

    model_config = {"from_attributes": True}


class RosterGenerateRequest(BaseModel):
    """触发阵容生成请求。"""

    topic_id: int
    # 允许前端覆盖话题原始人数（如调试），默认 None 表示沿用 topic.expert_count
    expert_count: int | None = Field(None, ge=2, le=6)


class RosterOut(BaseModel):
    """阵容响应（含主持人与专家，未确认前为候选态）。"""

    topic_id: int
    guests: list[GuestOut] = Field(default_factory=list)
    is_confirmed: bool = Field(False, description="是否已被用户确认进入演播厅")

    model_config = {"from_attributes": True}
