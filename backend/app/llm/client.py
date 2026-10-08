"""
LLM 客户端 — httpx 直调兼容 OpenAI 协议。

设计要点（PRD §7 安全要求）：
- API Key 仅在构造时从 settings 读取，写入 Authorization header，绝不通过 API 响应暴露
- 共享一个 httpx.AsyncClient 实例，避免每次请求重新建连
- 提供 chat / chat_stream / chat_json 三种调用模式：
  * chat：同步一次性返回完整文本
  * chat_stream：async generator，逐 delta 推送（用于 SSE 流式发言）
  * chat_json：强制 response_format=json_object，返回解析后的 dict（用于阵容/抽取）

依赖注入：FastAPI 路由通过 get_llm_client() 获取单例。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.config import settings


class LLMClient:
    """OpenAI 兼容协议的 LLM 客户端单例。

    不要直接实例化，请通过 get_llm_client() 获取。
    """

    def __init__(self, api_key: str, base_url: str, model: str, default_temperature: float) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is empty; configure it in .env")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_temperature = default_temperature
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def configured(self) -> bool:
        return bool(self._api_key) and not self._api_key.startswith("sk-replace-me")

    @property
    def model(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> str:
        """一次性返回完整文本。"""
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=False,
        )
        resp = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """流式返回 delta 文本片段。

        每个 yield 是一段文本增量，调用方拼接成完整内容。
        """
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=True,
        )
        async with self._client.stream(
            "POST", f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = chunk["choices"][0]["delta"].get("content")
                except (KeyError, IndexError):
                    continue
                if delta:
                    yield delta

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any] | list[Any]:
        """强制 JSON 模式，返回解析后的对象。

        失败时抛 LLMJsonError，含原始文本片段便于排查。
        """
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=None,
            stream=False,
            json_mode=True,
        )
        resp = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMJsonError(f"LLM returned non-JSON content: {exc}", raw=text) from exc

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None,
        max_tokens: int | None,
        stop: list[str] | None,
        stream: bool,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._default_temperature if temperature is None else temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop:
            payload["stop"] = stop
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload


class LLMJsonError(RuntimeError):
    """LLM 返回的内容不是合法 JSON。"""

    def __init__(self, msg: str, raw: str = "") -> None:
        super().__init__(msg)
        self.raw = raw


# --- 单例管理 ---

_client_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """FastAPI 依赖：返回全局 LLMClient 单例。

    若未配置 API Key，抛 ValueError，路由层应转 503。
    """
    global _client_instance
    if _client_instance is None:
        if not settings.is_llm_configured():
            raise ValueError("LLM API Key not configured. Set LLM_API_KEY in .env.")
        _client_instance = LLMClient(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
            default_temperature=settings.LLM_TEMPERATURE,
        )
    return _client_instance


async def shutdown_llm_client() -> None:
    """应用关闭时调用，关闭 httpx 连接池。"""
    global _client_instance
    if _client_instance is not None:
        await _client_instance.aclose()
        _client_instance = None
