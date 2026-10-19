"""The only place where settings turn into provider implementations."""

from dataclasses import dataclass

from app.core.config import Settings
from app.providers.asr.base import ASRProvider
from app.providers.asr.fake import FakeASR
from app.providers.asr.faster_whisper import FasterWhisperASR
from app.providers.embeddings.base import EmbeddingsProvider
from app.providers.embeddings.fake import FakeEmbeddings
from app.providers.embeddings.openai_compatible import OpenAICompatibleEmbeddings
from app.providers.llm.base import LLMProvider
from app.providers.llm.fake import FakeLLM
from app.providers.llm.openai_compatible import OpenAICompatibleLLM
from app.providers.ocr.base import OCRProvider
from app.providers.ocr.fake import FakeOCR
from app.providers.ocr.tesseract import TesseractOCR
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
    judge_llm: LLMProvider  # checks answers; the same model unless LLM_JUDGE_MODEL differs
    embeddings: EmbeddingsProvider
    asr: ASRProvider
    ocr: OCRProvider
    vlm: VLMProvider | None


def _llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        # Without a model the interviewer asks its fixed probe questions.
        return FakeLLM(unknown_text_raises=True)
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLM(settings, model=settings.llm_model)
    raise _not_yet("LLM", settings.llm_provider)


def _embeddings(settings: Settings) -> EmbeddingsProvider:
    if settings.embeddings_provider == "fake":
        return FakeEmbeddings(dim=settings.embeddings_dim)
    if settings.embeddings_provider == "openai_compatible":
        return OpenAICompatibleEmbeddings(settings)
    raise _not_yet("Embeddings", settings.embeddings_provider)


def _asr(settings: Settings) -> ASRProvider:
    if settings.asr_provider == "fake":
        return FakeASR()
    if settings.asr_provider == "faster_whisper":
        return FasterWhisperASR(settings)
    raise _not_yet("ASR", settings.asr_provider)


def _judge(settings: Settings, llm: LLMProvider) -> LLMProvider:
    judge_model = settings.effective_judge_model
    if settings.llm_provider == "openai_compatible" and judge_model != settings.llm_model:
        return OpenAICompatibleLLM(settings, model=judge_model)
    return llm


def _ocr(settings: Settings) -> OCRProvider:
    if settings.ocr_engine == "fake":
        return FakeOCR()
    if settings.ocr_engine == "tesseract":
        return TesseractOCR()
    raise _not_yet("OCR", settings.ocr_engine)


def build_providers(settings: Settings) -> Providers:
    llm = _llm(settings)
    return Providers(
        llm=llm,
        judge_llm=_judge(settings, llm),
        embeddings=_embeddings(settings),
        asr=_asr(settings),
        ocr=_ocr(settings),
        vlm=FakeVLM() if settings.vlm_enabled else None,
    )
