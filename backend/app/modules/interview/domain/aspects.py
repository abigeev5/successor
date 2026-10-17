"""Process aspects of the interview (SPEC 7.4): what a successor must know about every process."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Aspect:
    key: str
    label: str
    example: str  # sample probe question from the SPEC; also the fallback question (D-041)
    probe_type: str  # walkthrough | cue | exception | counterfactual | contact | timing


ASPECTS: tuple[Aspect, ...] = (
    Aspect(
        "purpose",
        "Зачем и что на выходе",
        "Для кого этот результат и что будет, если его не сделать вовремя?",
        "counterfactual",
    ),
    Aspect("trigger", "Когда запускается", "Что служит сигналом, что пора этим заниматься?", "cue"),
    Aspect("steps", "Шаги", "Расскажите, как вы делали это в последний раз, по шагам.", "walkthrough"),
    Aspect("tools", "Системы и инструменты", "В каких программах или таблицах это делается?", "cue"),
    Aspect("inputs", "Входные данные и документы", "Что нужно получить заранее и от кого?", "cue"),
    Aspect(
        "done_criteria",
        "Как понять, что готово",
        "По каким признакам вы понимаете, что можно отправлять?",
        "cue",
    ),
    Aspect(
        "exceptions",
        "Исключения",
        "Был ли случай, когда обычный порядок не сработал? Что вы сделали?",
        "exception",
    ),
    Aspect("pitfalls", "Типичные ошибки", "На чём чаще всего ошибаются новички?", "counterfactual"),
    Aspect(
        "contacts",
        "Люди и контакты",
        "К кому идти, если что-то пошло не так? Что лучше у него спросить?",
        "contact",
    ),
    Aspect("timing", "Сроки и календарь", "Есть ли горячие периоды или жёсткие дедлайны?", "timing"),
    Aspect("rationale", "Почему так", "Почему делается именно так, а не проще?", "counterfactual"),
)

BY_KEY: dict[str, Aspect] = {a.key: a for a in ASPECTS}
ASPECT_KEYS: tuple[str, ...] = tuple(BY_KEY)

# Which missing aspect to ask about first (SPEC 7.4).
PRIORITY: tuple[str, ...] = (
    "steps",
    "done_criteria",
    "exceptions",
    "pitfalls",
    "inputs",
    "contacts",
    "timing",
    "trigger",
    "tools",
    "purpose",
    "rationale",
)

COVERAGE_TARGET = 0.7  # move to the next process at >= 70 %
MAX_PROBE_STREAK = 2  # the same aspect at most twice in a row
