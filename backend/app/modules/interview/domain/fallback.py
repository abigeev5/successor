"""Fixed interviewer texts: steps that need no LLM, and fallbacks when the LLM fails (D-041)."""

from app.modules.interview.domain.aspects import BY_KEY
from app.modules.interview.domain.planner import NextStep, StepKind

MAP_COLLECT = (
    "Какие задачи вы выполняете регулярно — ежедневно, раз в месяц, раз в семестр? "
    "Перечислите их, даже небольшие."
)
CONFIRM_PROCESSES = (
    "Я выделил из ваших ответов задачи — они справа, в блоке «Карта обязанностей». "
    "Отметьте те, что действительно ваши, укажите частоту и важность и нажмите «Подтвердить»."
)
EXAMPLE_FOLLOWUP = "Можете привести конкретный пример — последний случай, когда так было?"
WRAPUP = "Что ещё обязательно должен знать ваш преемник, о чём я не спросил?"
FINISH = (
    "Спасибо! На сегодня всё. Из нашей беседы я подготовлю черновики карточек знаний — "
    "они появятся в разделе «Проверка карточек». В базу попадёт только то, что вы подтвердите."
)


def fallback_question(step: NextStep, process_name: str | None) -> str:
    if step.kind is StepKind.MAP_COLLECT:
        return MAP_COLLECT
    if step.kind is StepKind.CONFIRM_PROCESSES:
        return CONFIRM_PROCESSES
    if step.kind is StepKind.WALKTHROUGH:
        return f"Давайте разберём «{process_name}». Расскажите, как вы делали это в последний раз, по шагам."
    if step.kind is StepKind.EXAMPLE_FOLLOWUP:
        return EXAMPLE_FOLLOWUP
    if step.kind is StepKind.PROBE and step.aspect in BY_KEY:
        return BY_KEY[step.aspect].example
    if step.kind is StepKind.WRAPUP:
        return WRAPUP
    return FINISH
