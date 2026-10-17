"""The only place where settings turn into provider implementations (docs/architecture.md, 5.4)."""

from dataclasses import dataclass

from app.core.config import Settings
from app.providers.asr.base import ASRProvider
from app.providers.asr.fake import FakeASR
from app.providers.embeddings.base import EmbeddingsProvider
from app.providers.embeddings.fake import FakeEmbeddings
from app.providers.llm.base import LLMProvider
from app.providers.llm.fake import FakeLLM
from app.providers.ocr.base import OCRProvider
from app.providers.ocr.fake import FakeOCR
from app.providers.vlm.base import VLMProvider
from app.providers.vlm.fake import FakeVLM


class ProviderNotAvailable(RuntimeError):
    pass


def _not_yet(kind: str, value: str) -> ProviderNotAvailable:
    return ProviderNotAvailable(
        f"{kind}-провайдер «{value}» ещё не реализован (см. docs/plan.md). Укажите «fake» в .env."
    )


@dataclass
class Providers:
    llm: LLMProvider
    embeddings: EmbeddingsProvider
    asr: ASRProvider
    ocr: OCRProvider
    vlm: VLMProvider | None


def build_providers(settings: Settings) -> Providers:
    if settings.llm_provider != "fake":
        raise _not_yet("LLM", settings.llm_provider)
    if settings.embeddings_provider != "fake":
        raise _not_yet("Embeddings", settings.embeddings_provider)
    if settings.asr_provider != "fake":
        raise _not_yet("ASR", settings.asr_provider)
    if settings.ocr_engine != "fake":
        raise _not_yet("OCR", settings.ocr_engine)
    return Providers(
        llm=FakeLLM(),
        embeddings=FakeEmbeddings(dim=settings.embeddings_dim),
        asr=FakeASR(),
        ocr=FakeOCR(),
        vlm=FakeVLM() if settings.vlm_enabled else None,
    )
