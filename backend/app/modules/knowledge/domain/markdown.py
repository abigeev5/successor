"""Markdown helpers for texts that go to models and the search index."""

import re

_IMAGE = re.compile(r"[ \t]*!\[[^\]]*\]\([^)]*\)[ \t]*\n?")


def strip_images(markdown: str) -> str:
    """Screenshots in procedure cards (`![Шаг 1](/api/assets/…)`) carry no text for search or the LLM."""
    return _IMAGE.sub("", markdown).strip()
