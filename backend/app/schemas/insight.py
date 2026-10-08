"""
Insight schemas — 共识与分歧契约。

对齐 schema.md §3.5–§3.7 与 PRD §6.4 数据结构约束。
"""

from typing import Literal

from pydantic import BaseModel, Field

InsightType = Literal["consensus", "divergence"]
InsightStrength = Literal["weak", "medium", "strong"]


class InsightOut(BaseModel):
    """共识/分歧条目响应。"""

    id: int
    topic_id: int
    type: InsightType
    summary: str
    strength: InsightStrength
    version: int
    is_final: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class InsightWithLinksOut(InsightOut):
    """带关联发言与发言人的详情响应。"""

    guest_ids: list[int] = Field(default_factory=list, description="涉及发言人 ID")
    transcript_ids: list[int] = Field(default_factory=list, description="关联发言片段 ID")

    model_config = {"from_attributes": True}


class InsightStream(BaseModel):
    """SSE 推送的共识/分歧增量。

    action:
      - "create" 新增条目
      - "update" 修正强度/摘要（version+1）
      - "finalize" 收尾时标记最终版
    """

    topic_id: int
    insight_id: int
    action: Literal["create", "update", "finalize"]
    type: InsightType
    summary: str
    strength: InsightStrength
    version: int
    is_final: bool
