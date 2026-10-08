"""
Application configuration.

CRITICAL (PRD §7 安全要求): 大模型 API Key 只能放在后端，
从环境变量（.env）读取，不得硬编码、不得暴露到浏览器端。

实现要点：
- 使用 pydantic-settings 从 .env 与 os.environ 读取
- LLM_API_KEY 字段不通过任何 API 响应返回
- 提供 Settings 依赖注入，便于 FastAPI 路由获取 LLM 客户端配置
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，优先级：os.environ > .env 文件 > 默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- LLM ---
    # 必须从 .env 读取，绝不硬编码（PRD 安全约束）
    LLM_API_KEY: str = Field(
        default="",
        description="大模型 API Key，仅后端使用，不通过 API 响应暴露",
    )
    LLM_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        description="兼容 OpenAI 协议的大模型 Base URL",
    )
    LLM_MODEL: str = Field(
        default="deepseek-chat",
        description="大模型名称",
    )
    LLM_TEMPERATURE: float = Field(
        default=0.7,
        description="默认温度，各 Agent 可自行覆盖",
    )

    # --- App ---
    APP_ENV: Literal["dev", "test", "prod"] = Field(default="dev")
    APP_HOST: str = Field(default="0.0.0.0")
    APP_PORT: int = Field(default=8000)

    # --- Database ---
    DATABASE_URL: str = Field(
        default="sqlite:///./ai_panel_studio.db",
        description="SQLite 数据库 URL",
    )

    # --- 业务可调参数（对齐 PRD §3.3 调度策略） ---
    AGENT_CONTEXT_WINDOW_K: int = Field(
        default=8,
        description="每位 Agent 读取最近 K 条 Transcript 作为上下文",
    )
    DEFAULT_EXPERT_COUNT: int = Field(default=4)
    MAX_EXPERT_COUNT: int = Field(default=6)
    MIN_EXPERT_COUNT: int = Field(default=2)

    def is_llm_configured(self) -> bool:
        """校验 LLM 是否已配置真实 Key（非空且非占位符）。"""
        return bool(self.LLM_API_KEY) and not self.LLM_API_KEY.startswith("sk-replace-me")

    def llm_settings_safe(self) -> dict:
        """返回不含敏感 Key 的 LLM 配置，可用于日志或调试打印。"""
        return {
            "base_url": self.LLM_BASE_URL,
            "model": self.LLM_MODEL,
            "temperature": self.LLM_TEMPERATURE,
            "configured": self.is_llm_configured(),
        }


@lru_cache
def get_settings() -> Settings:
    """单例 Settings，避免重复 IO 读 .env。"""
    return Settings()


# 模块级便捷引用
settings = get_settings()
