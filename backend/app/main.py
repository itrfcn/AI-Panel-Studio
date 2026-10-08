"""
FastAPI 应用入口。

启动：
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings

app = FastAPI(
    title="AI Panel Studio API",
    description="AI 圆桌讨论 Web App MVP 后端（骨架版，LLM 调用待接入）",
    version="0.1.0",
)

# CORS：MVP 本地开发放开，生产按需收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    """启动时确保表存在（不 drop）。"""
    # 仅 create_all，不 drop；样例数据走 scripts/init_db.py
    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)


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
