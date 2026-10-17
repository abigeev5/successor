import json
import math
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.providers.asr.fake import FakeASR
from app.providers.embeddings.fake import FakeEmbeddings
from app.providers.llm.base import LLMError, LLMStructuredOutputError, Message
from app.providers.llm.fake import FakeLLM
from app.providers.ocr.fake import FakeOCR


class Answer(BaseModel):
    value: int


class Defaults(BaseModel):
    items: list[str] = []


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_fake_llm_rule_by_substring() -> None:
    llm = FakeLLM()
    llm.add_rule("пересдач", "Ответ про пересдачи")
    assert await llm.complete([Message("user", "Как оформить пересдачу?")]) == "Ответ про пересдачи"


async def test_fake_llm_unknown_prompt_gives_deterministic_stub() -> None:
    llm = FakeLLM()
    first = await llm.complete([Message("user", "Что-то новое")])
    assert first == await llm.complete([Message("user", "Что-то новое")])
    assert first.startswith("Заглушка FakeLLM")


async def test_fake_llm_without_model_raises_for_unknown_text() -> None:
    llm = FakeLLM(unknown_text_raises=True)
    llm.add_rule("известный", "ответ")
    assert await llm.complete([Message("user", "известный вопрос")]) == "ответ"
    with pytest.raises(LLMError):
        await llm.complete([Message("user", "новый вопрос")])
    assert await llm.complete_json([Message("user", "x")], Defaults) == Defaults()


async def test_fake_llm_sequential_responses_repeat_last() -> None:
    llm = FakeLLM()
    llm.add_rule("q", ["1", "2"])
    assert [await llm.complete([Message("user", "q")]) for _ in range(3)] == ["1", "2", "2"]


async def test_complete_json_retries_after_invalid_json() -> None:
    llm = FakeLLM()
    llm.add_rule("число", ["не json", '```json\n{"value": 7}\n```'])
    result = await llm.complete_json([Message("user", "Верни число")], Answer)
    assert result == Answer(value=7)
    # Second call contains the model's bad answer and the retry instruction from json_retry.md.
    retry_call = llm.calls[1]
    assert retry_call[-2] == Message("assistant", "не json")
    assert "не прошёл проверку" in retry_call[-1].content


async def test_complete_json_gives_up_after_three_attempts() -> None:
    llm = FakeLLM()
    llm.add_rule("число", '{"value": "abc"}')
    with pytest.raises(LLMStructuredOutputError):
        await llm.complete_json([Message("user", "Верни число")], Answer)
    assert len(llm.calls) == 3


async def test_complete_json_without_rule_uses_schema_defaults_or_fails() -> None:
    llm = FakeLLM()
    assert await llm.complete_json([Message("user", "x")], Defaults) == Defaults()
    with pytest.raises(LLMStructuredOutputError):
        await llm.complete_json([Message("user", "x")], Answer)


def test_fake_llm_loads_rules_from_dir(tmp_path: Path) -> None:
    (tmp_path / "rules.json").write_text(
        json.dumps([{"match": "a", "response": "b"}, {"match": "c", "response_json": {"value": 1}}]),
        encoding="utf-8",
    )
    llm = FakeLLM.from_dir(tmp_path)
    assert [r.responses for r in llm.rules] == [["b"], ['{"value": 1}']]


def test_fake_embeddings_are_deterministic_and_normalized() -> None:
    emb = FakeEmbeddings(dim=256)
    a, b = emb.embed(["Оформление пересдачи", "Оформление пересдачи"])
    assert a == b
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0)


def test_fake_embeddings_word_overlap_means_closer() -> None:
    emb = FakeEmbeddings(dim=1024)
    base, close, far = emb.embed(
        ["ведомость по экзамену группы", "ведомость по экзамену", "справка для военкомата"]
    )
    assert cosine(base, close) > cosine(base, far)


def test_fake_embeddings_treat_yo_as_e() -> None:
    emb = FakeEmbeddings(dim=64)
    assert emb.embed(["отчёт"]) == emb.embed(["отчет"])


def test_fake_asr_reads_neighbour_transcript(tmp_path: Path) -> None:
    audio = tmp_path / "answer.webm"
    audio.write_bytes(b"")
    (tmp_path / "answer.transcript.json").write_text(
        json.dumps({"segments": [{"start_ms": 0, "end_ms": 900, "text": "Сначала открываю портал"}]}),
        encoding="utf-8",
    )
    transcript = FakeASR().transcribe(audio)
    assert transcript.text == "Сначала открываю портал"


def test_fake_asr_without_transcript_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="транскрипта"):
        FakeASR().transcribe(tmp_path / "missing.webm")


def test_fake_ocr_reads_boxes_or_returns_empty(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    assert FakeOCR().read(image) == []
    (tmp_path / "frame.ocr.json").write_text(
        json.dumps([{"text": "+7 900 000-00-00", "x": 1, "y": 2, "width": 3, "height": 4}]), encoding="utf-8"
    )
    assert FakeOCR().read(image)[0].text == "+7 900 000-00-00"
