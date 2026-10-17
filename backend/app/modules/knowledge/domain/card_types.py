from enum import StrEnum


class CardType(StrEnum):
    PROCEDURE = "procedure"
    RULE = "rule"
    EXCEPTION = "exception"
    PITFALL = "pitfall"
    CONTACT = "contact"
    DEADLINE = "deadline"
    TERM = "term"


CARD_TYPE_LABELS: dict[CardType, str] = {
    CardType.PROCEDURE: "Инструкция",
    CardType.RULE: "Правило / признак",
    CardType.EXCEPTION: "Исключение",
    CardType.PITFALL: "Типичная ошибка",
    CardType.CONTACT: "К кому обращаться",
    CardType.DEADLINE: "Сроки",
    CardType.TERM: "Термин / жаргон",
}

# Which interview aspects a card type covers (SPEC 7.5); used for coverage by approved cards.
CARD_TYPE_ASPECTS: dict[CardType, tuple[str, ...]] = {
    CardType.PROCEDURE: ("steps", "tools", "inputs", "trigger"),
    CardType.RULE: ("done_criteria", "rationale", "purpose"),
    CardType.EXCEPTION: ("exceptions",),
    CardType.PITFALL: ("pitfalls",),
    CardType.CONTACT: ("contacts",),
    CardType.DEADLINE: ("timing",),
    CardType.TERM: (),
}
