import uuid

from app.modules.assistant.domain.claims import assemble, cited, claims, mentions_absence, parse_answer
from app.modules.assistant.domain.refusal import is_no_answer, refuse_before_llm
from app.modules.assistant.pipeline import DEGRADED_LEAD, Source, degraded_answer


def test_refuse_before_llm_only_without_any_relevant_signal() -> None:
    assert refuse_before_llm(None, 0, 0.45)
    assert refuse_before_llm(0.30, 0, 0.45)
    assert not refuse_before_llm(0.50, 0, 0.45)
    assert not refuse_before_llm(0.10, 2, 0.45)  # a full-text match is enough to try


def test_no_answer_marker() -> None:
    assert is_no_answer("NO_ANSWER")
    assert is_no_answer(" «no_answer» ")
    assert not is_no_answer("Ответ: NO_ANSWER")


def test_parse_splits_sentences_and_moves_citations_before_the_stop() -> None:
    [line] = parse_answer("Отчёт сдают до 5-го числа. [1] Подписывает начальник [2].")
    texts = [s.text for s in line.sentences]
    assert texts == ["Отчёт сдают до 5-го числа [1].", "Подписывает начальник [2]."]
    assert [s.citations for s in line.sentences] == [(1,), (2,)]


def test_notes_are_not_claims() -> None:
    lines = parse_answer(
        "Порядок такой:\n1. Проверить подписи [1].\n2. Отнести в деканат [2].\n"
        "В базе нет сведений о сроках хранения."
    )
    kinds = [s.note for line in lines for s in line.sentences]
    assert kinds == ["lead", "", "", "absence"]
    assert [c.text for c in claims(lines)] == ["Проверить подписи [1].", "Отнести в деканат [2]."]
    assert mentions_absence(lines)


def test_uncited_sentence_is_a_claim() -> None:
    [line] = parse_answer("Это надо сделать сразу.")
    assert not line.sentences[0].is_note
    assert not mentions_absence(parse_answer("Это надо сделать сразу."))


def test_assemble_drops_unsupported_and_renumbers() -> None:
    lines = parse_answer("Шаги:\n1. Первый [1].\n2. Выдуманный.\n3. Третий [2].\n\nИтог [1].")
    first, _, third, total = [c.id for c in claims(lines)]
    answer = assemble(lines, {first, third, total})
    assert answer == "Шаги:\n1. Первый [1].\n2. Третий [2].\n\nИтог [1]."
    assert cited(lines, {third, first}) == [1, 2]
    assert cited(lines, {third}) == [2]


def test_degraded_answer_lists_cards_with_citations() -> None:
    sources = [
        Source(1, uuid.uuid4(), "Срок отчёта", "rule", "До 5-го числа\nПодробности"),
        Source(2, uuid.uuid4(), "Подпись", "contact", "Звонить секретарю"),
    ]
    text = degraded_answer(sources)
    assert text.splitlines() == [
        DEGRADED_LEAD,
        "- **Срок отчёта** — До 5-го числа [1]",
        "- **Подпись** — Звонить секретарю [2]",
    ]
