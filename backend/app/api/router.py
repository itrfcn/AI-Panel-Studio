"""
API 路由聚合。

路由前缀约定（对齐 schema.md §8 API 契约概要）：
  - /api/topics            讨论列表/创建/详情/状态
  - /api/topics/:id/roster 阵容生成/确认
  - /api/topics/:id/stream SSE 实时流（Transcript + Insight）
  - /api/topics/:id/insights 共识与分歧
  - /api/topics/:id/replay 回放
"""

from fastapi import APIRouter

from app.api import insights, roster, stream, topics

api_router = APIRouter(prefix="/api")
api_router.include_router(topics.router)
api_router.include_router(roster.router)
api_router.include_router(stream.router)
api_router.include_router(insights.router)
