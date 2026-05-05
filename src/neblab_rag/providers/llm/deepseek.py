"""DeepSeek LLM provider (OpenAI-compatible).

Works with any OpenAI-compatible endpoint (DeepSeek, internal Qwen-served
DeepSeek, Spark, etc.) — pass ``base_url`` + ``default_model`` at construct
time. We name the class ``DeepSeekProvider`` because that is the v1 default
deployment, but it is fully provider-agnostic at the wire level.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.llm.base import (
    ChatRequest,
    ChatResponse,
    LLMProvider,
    StreamChunk,
)


class DeepSeekProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
        return {
            "model": request.model or self._default_model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stop": request.stop or None,
            "stream": stream,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(self, request: ChatRequest) -> ChatResponse:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResponse(
            content=choice["message"]["content"],
            model=data["model"],
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                method="POST",
                url=f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line.removeprefix("data: ")
                if payload == "[DONE]":
                    break
                obj = json.loads(payload)
                choices = obj.get("choices") or []
                if not choices:
                    # DeepSeek occasionally emits keepalive frames with no
                    # choices (e.g. usage-only payloads). Skip those.
                    continue
                choice = choices[0]
                # DeepSeek's terminal chunk ships {"delta": {"content": null},
                # "finish_reason": "stop"}. The dict-default trick doesn't help
                # because the key exists and is JSON null — coerce explicitly.
                delta = choice.get("delta", {}).get("content") or ""
                yield StreamChunk(
                    delta=delta,
                    finish_reason=choice.get("finish_reason"),
                )
