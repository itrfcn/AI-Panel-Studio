"""
LLM 客户端 — httpx 直调兼容 OpenAI 协议。

设计要点（PRD §7 安全要求）：
- API Key 仅在构造时从 settings 读取，写入 Authorization header，绝不通过 API 响应暴露
- 共享一个 httpx.AsyncClient 实例，避免每次请求重新建连
- 提供 chat / chat_stream / chat_json 三种调用模式：
  * chat：同步一次性返回完整文本
  * chat_stream：async generator，逐 delta 推送（用于 SSE 流式发言）
  * chat_json：强制 response_format=json_object，返回解析后的 dict（用于阵容/抽取）

容错：
- 部分兼容厂商在上游过载时返回 HTTP 200 + SSE 错误帧 {"error": {...}}，
  客户端识别为 LLMUpstreamError 并指数退避重试（最多 3 次）。
- 流式调用仅在"尚未产出任何 delta"时重试，避免内容重复；已产出后失败由调用方处理。

依赖注入：FastAPI 路由通过 get_llm_client() 获取单例。
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from app.config import settings

T = TypeVar("T")

# 重试参数
_MAX_RETRIES = 3
_BASE_DELAY = 2.0


class LLMUpstreamError(RuntimeError):
    """上游 LLM 服务错误（过载/5xx/429/流体内嵌 error 帧），可重试。"""


class LLMJsonError(RuntimeError):
    """LLM 返回的内容不是合法 JSON。"""

    def __init__(self, msg: str, raw: str = "") -> None:
        super().__init__(msg)
        self.raw = raw


def _is_retryable(exc: Exception) -> bool:
    """判断异常是否值得重试。"""
    if isinstance(exc, LLMUpstreamError):
        return True
    if isinstance(exc, httpx.TransportError):
        return True  # 连接超时、读超时、断连等
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (408, 409, 429, 500, 502, 503, 504)
    return False


async def _retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    label: str = "llm",
    max_retries: int = _MAX_RETRIES,
) -> T:
    """对非流式调用做指数退避重试。"""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_retries or not _is_retryable(exc):
                raise
            delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    # 理论不可达
    raise last_exc if last_exc else RuntimeError(f"{label} failed without exception")


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
            timeout=httpx.Timeout(90.0, connect=10.0),
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

    # ------------------------------------------------------------------
    # 非流式
    # ------------------------------------------------------------------

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

        async def _once() -> str:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            self._raise_if_error_payload(data)
            return data["choices"][0]["message"]["content"] or ""

        return await _retry_async(_once, label="chat")

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

        async def _once():
            resp = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            self._raise_if_error_payload(data)
            return data["choices"][0]["message"]["content"] or ""

        text = await _retry_async(_once, label="chat_json")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMJsonError(f"LLM returned non-JSON content: {exc}", raw=text) from exc

    # ------------------------------------------------------------------
    # 流式
    # ------------------------------------------------------------------

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

        重试语义：仅在"尚未向调用方产出任何 delta"时重试
        （供应商过载/网络错误）；一旦已 yield 内容就不再重试，避免重复。
        """
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            stream=True,
        )

        for attempt in range(_MAX_RETRIES + 1):
            produced = 0
            try:
                async for delta in self._stream_once(payload):
                    produced += 1
                    yield delta
                return  # 正常结束
            except Exception as exc:  # noqa: BLE001
                # 已产出内容：不能重试（会重复），向上抛由调用方处理
                if produced > 0 or attempt >= _MAX_RETRIES or not _is_retryable(exc):
                    raise
                delay = _BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                # 继续下一次尝试

    async def _stream_once(self, payload: dict[str, Any]) -> AsyncIterator[str]:
        """发起一次流式请求并逐 delta yield。识别供应商内嵌错误帧。"""
        async with self._client.stream(
            "POST", f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                stripped = line.strip()
                if not stripped.startswith("data:"):
                    continue
                data_str = stripped[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                # 供应商在 HTTP 200 流体内嵌错误帧：{"error": {...}}
                err = chunk.get("error") if isinstance(chunk, dict) else None
                if err:
                    raise LLMUpstreamError(
                        f"LLM upstream error in stream: "
                        f"{err.get('message') if isinstance(err, dict) else err}"
                    )
                choices = chunk.get("choices") or []
                if not choices:
                    # usage 帧等：choices 为空，跳过
                    continue
                try:
                    delta = choices[0].get("delta", {}).get("content")
                except (AttributeError, IndexError):
                    continue
                if delta:
                    yield delta

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _raise_if_error_payload(data: Any) -> None:
        """非流式响应体内嵌错误（部分厂商 HTTP 200 + body.error）。"""
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise LLMUpstreamError(f"LLM upstream error: {msg}")

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
