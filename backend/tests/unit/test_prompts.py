from pathlib import Path

import pytest
from jinja2 import UndefinedError

from app.core.prompts import PromptError, PromptRegistry, get_prompts, parse_front_matter


def write(tmp_path: Path, name: str, text: str) -> PromptRegistry:
    (tmp_path / f"{name}.md").write_text(text, encoding="utf-8")
    return PromptRegistry(tmp_path)


def test_render_with_version(tmp_path: Path) -> None:
    registry = write(tmp_path, "hello", "---\nversion: 3\n---\nПривет, {{ name }}!\n")
    rendered = registry.render("hello", name="Ирина")
    assert (rendered.name, rendered.version, rendered.text) == ("hello", "3", "Привет, Ирина!")


def test_missing_variable_is_an_error(tmp_path: Path) -> None:
    registry = write(tmp_path, "hello", "---\nversion: 1\n---\n{{ name }}")
    with pytest.raises(UndefinedError):
        registry.render("hello")


def test_prompt_without_version_is_rejected(tmp_path: Path) -> None:
    registry = write(tmp_path, "bad", "Текст без заголовка")
    with pytest.raises(PromptError, match="version"):
        registry.render("bad")


def test_unknown_prompt(tmp_path: Path) -> None:
    with pytest.raises(PromptError, match="not found"):
        PromptRegistry(tmp_path).render("nope")


def test_unclosed_front_matter() -> None:
    with pytest.raises(PromptError):
        parse_front_matter("---\nversion: 1\nтекст")


def test_all_repository_prompts_have_versions() -> None:
    registry = get_prompts()
    names = [p.stem for p in Path(registry._dir).glob("*.md")]
    assert names, "no prompts found"
    for name in names:
        assert registry.version(name)
