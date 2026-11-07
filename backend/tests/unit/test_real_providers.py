"""Real providers against mocked HTTP / a fake faster-whisper module: no models, no network."""

import json
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.http import OfflineModeViolation
from app.providers.asr.faster_whisper import FasterWhisperASR
from app.providers.embeddings.openai_compatible import EmbeddingsError, OpenAICompatibleEmbeddings
from app.providers.llm.base import LLMError, LLMStructuredOutputError, Message
from app.providers.llm.openai_compatible import OpenAICompatibleLLM, strip_thinking
from app.providers.registry import ProviderNotAvailable, build_providers


class Verdict(BaseModel):
    supported: bool
    reason: str


def chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def make_llm(handler: Any, **settings: Any) -> tuple[OpenAICompatibleLLM, list[dict[str, Any]]]:
    seen: list[dict[str, Any]] = []

    def recorder(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content or b"{}")})
        return handler(request)

    cfg = Settings(llm_base_url="http://localhost:8080/v1", llm_model="qwen", **settings)
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    return OpenAICompatibleLLM(cfg, model=cfg.llm_model, client=client), seen


async def test_complete_sends_openai_payload() -> None:
    llm, seen = make_llm(lambda r: chat_response("Расскажите про последний раз."))
    answer = await llm.complete(
        [Message("system", "Ты интервьюер"), Message("user", "Привет")], temperature=0.3
    )
    assert answer == "Расскажите про последний раз."
    assert seen[0]["url"] == "http://localhost:8080/v1/chat/completions"
    body = seen[0]["body"]
    assert body["model"] == "qwen" and body["temperature"] == 0.3
    assert body["messages"] == [
        {"role": "system", "content": "Ты интервьюер"},
        {"role": "user", "content": "Привет"},
    ]


async def test_complete_json_uses_json_schema_and_validates() -> None:
    llm, seen = make_llm(lambda r: chat_response('{"supported": true, "reason": "есть в источнике"}'))
    result = await llm.complete_json([Message("user", "Проверь")], Verdict)
    assert result == Verdict(supported=True, reason="есть в источнике")
    fmt = seen[0]["body"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["schema"]["required"] == ["supported", "reason"]


async def test_complete_json_retries_and_gives_up() -> None:
    llm, seen = make_llm(lambda r: chat_response("не json"))
    with pytest.raises(LLMStructuredOutputError):
        await llm.complete_json([Message("user", "Проверь")], Verdict)
    assert len(seen) == 3


@pytest.mark.parametrize(("mode", "expected"), [("json_object", {"type": "json_object"}), ("none", None)])
async def test_json_modes(mode: str, expected: dict[str, str] | None) -> None:
    llm, seen = make_llm(lambda r: chat_response('{"supported": false, "reason": "-"}'), llm_json_mode=mode)
    await llm.complete_json([Message("user", "x")], Verdict)
    assert seen[0]["body"].get("response_format") == expected


async def test_http_errors_become_llm_error() -> None:
    llm, _ = make_llm(lambda r: httpx.Response(503, text="loading model"))
    with pytest.raises(LLMError, match="503"):
        await llm.complete([Message("user", "x")])

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    llm, _ = make_llm(boom)
    with pytest.raises(LLMError, match="недоступен"):
        await llm.complete([Message("user", "x")])


async def test_unexpected_payload_is_llm_error() -> None:
    llm, _ = make_llm(lambda r: httpx.Response(200, json={"error": "?"}))
    with pytest.raises(LLMError):
        await llm.complete([Message("user", "x")])


async def test_stream_parses_sse() -> None:
    sse = (
        'data: {"choices":[{"delta":{"content":"При"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"вет"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    llm, _ = make_llm(lambda r: httpx.Response(200, text=sse))
    assert [chunk async for chunk in llm.stream([Message("user", "x")])] == ["При", "вет"]


async def test_offline_mode_blocks_external_llm() -> None:
    cfg = Settings(llm_base_url="http://8.8.8.8/v1", offline_mode=True)
    llm = OpenAICompatibleLLM(cfg, model="")
    with pytest.raises(OfflineModeViolation):
        await llm.complete([Message("user", "x")])


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("<think>рассуждаю</think>\nВопрос?", "Вопрос?"),
        ("рассуждаю</think>Вопрос?", "Вопрос?"),
        ("Вопрос?", "Вопрос?"),
    ],
)
def test_strip_thinking(raw: str, clean: str) -> None:
    assert strip_thinking(raw) == clean


def test_embeddings_are_sorted_normalized_and_checked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["input"] == ["а", "б"]
        return httpx.Response(
            200, json={"data": [{"index": 1, "embedding": [0.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}]}
        )

    cfg = Settings(embeddings_base_url="http://localhost:8081/v1", embeddings_dim=2)
    emb = OpenAICompatibleEmbeddings(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert emb.embed(["а", "б"]) == [[0.6, 0.8], [0.0, 1.0]]
    assert emb.embed([]) == []

    wrong_dim = Settings(embeddings_base_url="http://localhost:8081/v1", embeddings_dim=1024)
    emb = OpenAICompatibleEmbeddings(wrong_dim, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(EmbeddingsError, match="EMBEDDINGS_DIM"):
        emb.embed(["а", "б"])


def test_faster_whisper_provider_maps_segments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    created: list[dict[str, Any]] = []

    class FakeWhisperModel:
        def __init__(self, model: str, **kwargs: Any) -> None:
            created.append({"model": model, **kwargs})

        def transcribe(self, path: str, **kwargs: Any) -> tuple[Any, Any]:
            assert kwargs["language"] == "ru" and kwargs["word_timestamps"] is True
            word = types.SimpleNamespace(start=0.0, end=0.4, word=" Сначала")
            segment = types.SimpleNamespace(
                start=0.0, end=1.25, text=" Сначала открываю портал.", words=[word]
            )
            return iter([segment]), types.SimpleNamespace(duration=1.5)

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel))
    asr = FasterWhisperASR(Settings(asr_model="small", asr_device="cpu", asr_compute_type="int8"))
    transcript = asr.transcribe(tmp_path / "a.webm")
    asr.transcribe(tmp_path / "b.webm")

    assert len(created) == 1  # the model is loaded once, lazily
    assert created[0] == {"model": "small", "device": "cpu", "compute_type": "int8", "download_root": None}
    assert transcript.text == "Сначала открываю портал."
    assert transcript.duration_ms == 1500
    assert transcript.segments[0].end_ms == 1250
    assert transcript.segments[0].words[0].word == "Сначала"


def test_registry_builds_real_providers_without_loading_models() -> None:
    providers = build_providers(
        Settings(
            llm_provider="openai_compatible",
            llm_base_url="http://host.docker.internal:8080/v1",
            embeddings_provider="openai_compatible",
            embeddings_base_url="http://host.docker.internal:8081/v1",
            asr_provider="faster_whisper",
        )
    )
    assert (providers.llm.name, providers.embeddings.name, providers.asr.name) == (
        "openai_compatible",
        "openai_compatible",
        "faster_whisper",
    )


def test_registry_reports_missing_url_and_unimplemented() -> None:
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        build_providers(Settings(llm_provider="openai_compatible", llm_base_url=""))
    with pytest.raises(ProviderNotAvailable):
        build_providers(Settings(llm_provider="gigachat"))
