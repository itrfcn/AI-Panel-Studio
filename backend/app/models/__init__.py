"""
ORM 模型聚合包。

导入顺序刻意安排为：topic → guest → transcript → event_point → insight
保证外键依赖在被引用方先注册到 Base.metadata。
"""

from app.models.topic import Topic
from app.models.guest import Guest
from app.models.transcript import Transcript
from app.models.event_point import EventPoint
from app.models.insight import (
    Insight,
    InsightGuest,
    InsightSpeech,
    ReasoningChain,
)

__all__ = [
    "Topic",
    "Guest",
    "Transcript",
    "EventPoint",
    "Insight",
    "InsightGuest",
    "InsightSpeech",
    "ReasoningChain",
]
