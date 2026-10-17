"""FakeLLM for tests and demo without a model (SPEC, 5.3).

Answers come from rules: {"match": "<substring>", "response": "<text>" | ["<1st call>", "<2nd call>", ...]}
or {"match": ..., "response_json": {...}}. A rule matches if its substring occurs in any message.
Rules are passed directly or loaded from *.json files (each file holds a list of rules).
A list of responses is returned one by one; the last one repeats.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.providers.llm.base import LLMStructuredOutputError, Message, T
from app.providers.llm.structured import complete_json_with_retries


@dataclass
class FakeRule:
    match: str
    responses: list[str]
    calls: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FakeRule":
        if "response_json" in raw:
            responses = [json.dumps(raw["response_json"], ensure_ascii=False)]
        else:
            value = raw["response"]
            responses = value if isinstance(value, list) else [value]
        return cls(match=raw["match"], responses=[str(r) for r in responses])

    def next_response(self) -> str:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


@dataclass
class FakeLLM:
    rules: list[FakeRule] = field(default_factory=list)
    name: str = "fake"
    model: str = "fake"
    calls: list[list[Message]] = field(default_factory=list)

    @classmethod
    def from_dir(cls, directory: Path | None) -> "FakeLLM":
        rules: list[FakeRule] = []
        if directory is not None and directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                rules += [FakeRule.from_dict(r) for r in json.loads(path.read_text(encoding="utf-8"))]
        return cls(rules=rules)

    def add_rule(self, match: str, response: str | list[str]) -> None:
        self.rules.append(FakeRule(match, response if isinstance(response, list) else [response]))

    def _find(self, messages: list[Message]) -> FakeRule | None:
        text = "\n".join(m.content for m in messages)
        return next((r for r in self.rules if r.match in text), None)

    async def _raw(self, messages: list[Message]) -> str:
        self.calls.append(list(messages))
        rule = self._find(messages)
        if rule is not None:
            return rule.next_response()
        last = messages[-1].content if messages else ""
        return f"Заглушка FakeLLM: ответ на «{last[:60]}»"

    async def complete(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        return await self._raw(messages)

    async def complete_json(self, messages: list[Message], schema: type[T], *, temperature: float = 0.0) -> T:
        if self._find(messages) is None:
            # No canned answer: a schema whose fields all have defaults still works.
            try:
                return schema.model_validate({})
            except ValidationError as exc:
                raise LLMStructuredOutputError(
                    f"FakeLLM: нет заготовленного ответа для {schema.__name__}"
                ) from exc
        return await complete_json_with_retries(self._raw, messages, schema)

    async def stream(self, messages: list[Message], *, temperature: float = 0.2) -> AsyncIterator[str]:
        text = await self._raw(messages)
        for i in range(0, len(text), 16):
            yield text[i : i + 16]

    async def health(self) -> bool:
        return True
