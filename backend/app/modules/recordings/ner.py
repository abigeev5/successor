"""Person names with natasha NER. Loaded on first use (~4 s), then kept in the process."""

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _models() -> tuple[Any, Any]:
    from natasha import NewsEmbedding, NewsNERTagger, Segmenter

    return Segmenter(), NewsNERTagger(NewsEmbedding())


def find_persons(text: str) -> list[tuple[int, int]]:
    from natasha import Doc

    segmenter, tagger = _models()
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_ner(tagger)
    return [(span.start, span.stop) for span in doc.spans if span.type == "PER"]
