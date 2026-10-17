"""Structured output with validation and retries (SPEC, 5.2): shared by all LLM providers."""

import json
from collections.abc import Awaitable, Callable

from pydantic import ValidationError

from app.core.prompts import get_prompts
from app.providers.llm.base import LLMStructuredOutputError, Message, T

MAX_ATTEMPTS = 3  # first try + 2 retries


def extract_json(text: str) -> str:
    """Strips markdown fences and surrounding prose; returns the outermost JSON object/array."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return text
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start : end + 1] if end > start else text[start:]


async def complete_json_with_retries(
    raw_complete: Callable[[list[Message]], Awaitable[str]],
    messages: list[Message],
    schema: type[T],
    *,
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    history = list(messages)
    last_error = ""
    for _ in range(max_attempts):
        answer = await raw_complete(history)
        try:
            return schema.model_validate_json(extract_json(answer))
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)[:1000]
            retry = get_prompts().render("json_retry", error=last_error).text
            history = [*history, Message("assistant", answer), Message("user", retry)]
    raise LLMStructuredOutputError(
        f"Модель не вернула корректный JSON для {schema.__name__} за {max_attempts} попытки: {last_error}"
    )
