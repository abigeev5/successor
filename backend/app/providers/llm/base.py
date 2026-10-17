from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """The model server failed: network, timeout, HTTP error, unexpected response."""


class LLMStructuredOutputError(LLMError):
    """The model did not return valid JSON for the schema after all attempts (SPEC, 5.2)."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str: ...

    async def complete_json(
        self, messages: list[Message], schema: type[T], *, temperature: float = 0.0
    ) -> T: ...

    def stream(self, messages: list[Message], *, temperature: float = 0.2) -> AsyncIterator[str]: ...

    async def health(self) -> bool: ...
