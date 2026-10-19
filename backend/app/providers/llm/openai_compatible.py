"""LLM over an OpenAI-compatible HTTP API: llama.cpp `llama-server`, vLLM, Ollama, LM Studio.

POST {base_url}/chat/completions. Structured output uses `response_format`, so the server
constrains generation with a grammar; the answer is still validated by Pydantic with retries.
"""

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.core.http import make_http_client
from app.providers.llm.base import LLMError, Message, T
from app.providers.llm.structured import complete_json_with_retries

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Reasoning models (Qwen3 etc.) may put <think>…</think> into the content."""
    text = _THINK.sub("", text)
    if "</think>" in text:  # opening tag was cut off by the server's chat template
        text = text.split("</think>", 1)[1]
    return text.strip()


def response_format(schema: type[BaseModel], mode: str) -> dict[str, Any] | None:
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


class OpenAICompatibleLLM:
    name = "openai_compatible"

    def __init__(self, settings: Settings, *, model: str, client: httpx.AsyncClient | None = None) -> None:
        if not settings.llm_base_url:
            raise ValueError("LLM_BASE_URL не задан")
        self.model = model
        self._base = settings.llm_base_url.rstrip("/")
        self._json_mode = settings.llm_json_mode
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
        self._client = client or make_http_client(settings, headers=headers)

    def _payload(
        self, messages: list[Message], temperature: float, max_tokens: int, **extra: Any
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **extra,
        }
        if self.model:  # llama-server serves one model and ignores the name; others need it
            payload["model"] = self.model
        return payload

    async def _chat(self, payload: dict[str, Any]) -> str:
        try:
            response = await self._client.post(f"{self._base}/chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM-сервер ответил {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM-сервер недоступен: {type(exc).__name__}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("Неожиданный формат ответа LLM-сервера") from exc
        return strip_thinking(content or "")

    async def complete(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        return await self._chat(self._payload(messages, temperature, max_tokens))

    async def complete_json(self, messages: list[Message], schema: type[T], *, temperature: float = 0.0) -> T:
        fmt = response_format(schema, self._json_mode)
        extra = {"response_format": fmt} if fmt else {}

        async def raw(history: list[Message]) -> str:
            return await self._chat(self._payload(history, temperature, 4096, **extra))

        return await complete_json_with_retries(raw, messages, schema)

    async def stream(self, messages: list[Message], *, temperature: float = 0.2) -> AsyncIterator[str]:
        payload = self._payload(messages, temperature, 1024, stream=True)
        try:
            async with self._client.stream(
                "POST", f"{self._base}/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM-сервер недоступен: {type(exc).__name__}") from exc

    async def health(self) -> bool:
        try:
            response = await self._client.get(f"{self._base}/models", timeout=5)
            return response.status_code == 200
        except httpx.HTTPError:
            return False
