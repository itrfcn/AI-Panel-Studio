"""
Transcript schemas — 实时发言流契约。

对齐 schema.md §3.3 与 PRD §4.3。
SSE 推送用 TranscriptStream（含状态/部分内容）。
"""

from typing import Literal

from pydantic import BaseModel, Field

SpeechType = Literal["opening", "followup", "rebute", "supplement", "grab", "summary"]
SpeechStatus = Literal["pending", "streaming", "done", "aborted"]


class TranscriptOut(BaseModel):
    """发言完整响应。"""

    id: int
    topic_id: int
    guest_id: int
    turn_index: int
    content: str
    speech_type: SpeechType
    status: SpeechStatus
    started_at: str | None = None
    completed_at: str | None = None

    model_config = {"from_attributes": True}


class TranscriptStream(BaseModel):
    """SSE 推送的事件片段。

    - status=streaming 时 content 为流式增量
    - status=done 时 content 为最终完整文本
    - status=aborted 时携带 reason
    """

    topic_id: int
    transcript_id: int
    guest_id: int
    guest_name: str = Field(..., description="发言人姓名（前端直接展示）")
    guest_color: str = Field(..., description="发言人颜色")
    turn_index: int
    speech_type: SpeechType
    status: SpeechStatus
    delta: str = Field("", description="本次增量文本")
    content: str = Field("", description="累计完整文本（done 时填充）")
    reason: str | None = Field(None, description="aborted 原因")

    model_config = {"from_attributes": True}
