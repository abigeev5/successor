import uuid

import pytest

from app.modules.knowledge.domain.dedup import find_duplicate
from app.modules.knowledge.domain.quotes import find_quote, is_quotable, normalize
from app.modules.knowledge.domain.sources import SourceFragment, SourceRef, SourceType
from app.modules.knowledge.domain.windows import make_windows
from app.modules.knowledge.extraction import CardCandidate, QuoteRef, validate_quotes
from app.modules.org.domain.matching import match_name

ANSWER = (
    "Ведомость отправляю в деканат, только когда стоят ВСЕ подписи экзаменаторов. "
    "Если подписи нет — звоню на кафедру, секретарю, а не преподавателю: так быстрее.\n\n"
    "Ещё проверяю, что ёмкость аудитории не превышена."
)


def test_normalize() -> None:
    assert normalize("  «Ёлки,  Палки!»\n") == "елки, палки"


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("только когда стоят ВСЕ подписи экзаменаторов", "только когда стоят ВСЕ подписи экзаменаторов"),
        ("«Только когда стоят все подписи экзаменаторов.»", "только когда стоят ВСЕ подписи экзаменаторов"),
        ("емкость аудитории не превышена", "ёмкость аудитории не превышена"),
        ("звоню на кафедру,   секретарю", "звоню на кафедру, секретарю"),
        ("звоню на кафедру секретарю а не преподавателю", "звоню на кафедру, секретарю, а не преподавателю"),
    ],
)
def test_quote_is_found_and_original_span_returned(quote: str, expected: str) -> None:
    match = find_quote(quote, ANSWER)
    assert match is not None
    assert match.text == expected


def test_typo_in_quote_is_tolerated() -> None:
    match = find_quote("звоню на кафедру секритарю", ANSWER)
    assert match is not None and match.text.startswith("звоню на кафедру")


@pytest.mark.parametrize(
    "quote",
    [
        "отправляю ведомость по электронной почте ректору",  # not in the text
        "все подписи",  # too short
        "да",
    ],
)
def test_bad_quotes_are_rejected(quote: str) -> None:
    assert find_quote(quote, ANSWER) is None


def test_short_quote_rules() -> None:
    assert not is_quotable("звоню секретарю")  # 2 words
    assert is_quotable("звоню на кафедру секретарю")


def test_quote_longer_than_fragment() -> None:
    fragment = "Справку делаю за один день."
    assert find_quote("Справку делаю за один день", fragment) is not None
    assert find_quote("Справку делаю за один день, а иногда за два часа, если срочно", fragment) is None


def _fragment(text: str) -> SourceFragment:
    return SourceFragment(
        ref=SourceRef(SourceType.INTERVIEW_MESSAGE, uuid.uuid4()), text=text, label="Реплика"
    )


def test_validate_quotes_keeps_real_ones_and_drops_others() -> None:
    fragments = [_fragment("Первая реплика без нужного текста."), _fragment(ANSWER)]
    card = CardCandidate(
        type="rule",
        title="Когда отправлять ведомость",
        quotes=[
            QuoteRef(fragment=2, text="только когда стоят все подписи экзаменаторов"),
            QuoteRef(fragment=2, text="Только когда стоят ВСЕ подписи экзаменаторов"),  # same span twice
            QuoteRef(fragment=1, text="только когда стоят все подписи экзаменаторов"),  # wrong fragment
            QuoteRef(fragment=7, text="только когда стоят все подписи экзаменаторов"),  # no such fragment
        ],
    )
    sources = validate_quotes(card, fragments)
    assert [(s.fragment.ref, s.quote) for s in sources] == [
        (fragments[1].ref, "только когда стоят ВСЕ подписи экзаменаторов")
    ]


def test_card_without_evidence_has_no_sources() -> None:
    card = CardCandidate(
        type="rule", title="Выдумка", quotes=[QuoteRef(fragment=1, text="этого никто не говорил")]
    )
    assert validate_quotes(card, [_fragment(ANSWER)]) == []


def test_windows_overlap_by_one_fragment() -> None:
    assert make_windows([10] * 5, max_chars=25) == [range(0, 2), range(1, 3), range(2, 4), range(3, 5)]
    assert make_windows([10, 10], max_chars=100) == [range(0, 2)]
    assert make_windows([100, 5], max_chars=25) == [range(0, 1), range(1, 2)]
    assert make_windows([]) == []


def test_find_duplicate_threshold() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    existing = [(a, [1.0, 0.0]), (b, [0.6, 0.8])]
    assert find_duplicate([1.0, 0.0], existing) == (a, 1.0)
    assert find_duplicate([0.8, 0.6], existing) == (b, pytest.approx(0.96))  # cos to a = 0.8
    assert find_duplicate([0.0, 1.0], existing) is None  # cos 0.0 and 0.8


def test_match_process_name() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    processes = [
        (a, "Оформление пересдач"),
        (b, "Отчёт о движении контингента"),
        (c, "Отчёт по успеваемости"),
    ]
    assert match_name("отчет по контингенту", processes) == b  # other case endings
    assert match_name("Оформление пересдач.", processes) == a
    assert match_name("пересдачи", processes) == a
    assert match_name("отчет об успеваемости", processes) == c
    assert match_name("отчёт", processes) is None  # ambiguous: two reports
    assert match_name("Закупка канцтоваров", processes) is None
    assert match_name(None, processes) is None
