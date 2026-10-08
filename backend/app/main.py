"""
FastAPI 应用入口。

启动：
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动建表 + 预热 LLMClient；关闭时清理 httpx。"""
    # startup
    Base.metadata.create_all(bind=engine)
    # 预热 LLMClient 单例（仅当已配置 Key），便于首请求不卡建连
    if settings.is_llm_configured():
        try:
            from app.llm import get_llm_client

            get_llm_client()
        except Exception:  # noqa: BLE001 — 启动期不阻断
            pass
    yield
    # shutdown
    from app.llm import shutdown_llm_client
    from app.stream.runner import shutdown_all_sessions

    await shutdown_all_sessions()
    await shutdown_llm_client()


app = FastAPI(
    title="AI Panel Studio API",
    description="AI 圆桌讨论 Web App 后端（主持人开场/收尾已接入 LLM）",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS：MVP 本地开发放开，生产按需收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "llm": settings.llm_settings_safe(),  # 不含 API Key
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "name": "AI Panel Studio API",
        "docs": "/docs",
        "endpoints": {
            "topics": "/api/topics",
            "roster": "/api/topics/{topic_id}/roster",
            "stream": "/api/topics/{topic_id}/stream",
            "insights": "/api/topics/{topic_id}/insights",
        },
    }


app.include_router(api_router)
