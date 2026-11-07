"""Prompt templates: backend/app/prompts/<name>.md, Jinja2, with a front matter header:

    ---
    version: 1
    ---
    Template text...

The version goes to logs and eval reports so runs with different prompts can be compared.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PromptError(Exception):
    pass


@dataclass(frozen=True)
class RenderedPrompt:
    name: str
    version: str
    text: str


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end == -1:
        raise PromptError("Front matter is not closed with '---'")
    meta: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        if line.strip():
            key, sep, value = line.partition(":")
            if not sep:
                raise PromptError(f"Bad front matter line: {line!r}")
            meta[key.strip()] = value.strip()
    return meta, raw[end + len("\n---\n") :]


class PromptRegistry:
    def __init__(self, directory: Path = PROMPTS_DIR) -> None:
        self._dir = directory
        self._env = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=False)
        self._cache: dict[str, tuple[str, Any]] = {}

    def _load(self, name: str) -> tuple[str, Any]:
        if name not in self._cache:
            path = self._dir / f"{name}.md"
            if not path.is_file():
                raise PromptError(f"Prompt {name!r} not found in {self._dir}")
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            if "version" not in meta:
                raise PromptError(f"Prompt {name!r} has no version in front matter")
            self._cache[name] = (meta["version"], self._env.from_string(body))
        return self._cache[name]

    def version(self, name: str) -> str:
        return self._load(name)[0]

    def render(self, name: str, /, **context: Any) -> RenderedPrompt:
        # `name` is positional-only so templates may use a variable called "name".
        version, template = self._load(name)
        return RenderedPrompt(name=name, version=version, text=template.render(**context).strip())


@lru_cache
def get_prompts() -> PromptRegistry:
    return PromptRegistry()
