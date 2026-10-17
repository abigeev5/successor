"""The two LLM calls of an interview turn: analyze_turn (JSON) and the next question (text)."""

import logging

from app.core.prompts import get_prompts
from app.modules.interview.domain.analysis import TurnAnalysis
from app.modules.interview.domain.aspects import ASPECTS, BY_KEY
from app.modules.interview.domain.fallback import fallback_question
from app.modules.interview.domain.planner import NextStep, StepKind
from app.providers.llm.base import LLMError, LLMProvider, Message

log = logging.getLogger(__name__)
RECENT_TURNS = 6
LLM_STEPS = {StepKind.WALKTHROUGH, StepKind.PROBE, StepKind.EXAMPLE_FOLLOWUP, StepKind.WRAPUP}


def format_turns(turns: list[tuple[str, str]]) -> str:
    """turns: (role, content) with role 'interviewer' | 'expert'."""
    names = {"interviewer": "Интервьюер", "expert": "Сотрудник"}
    return "\n".join(f"{names.get(role, role)}: {content}" for role, content in turns[-RECENT_TURNS:])


async def analyze_turn(
    llm: LLMProvider, *, processes: list[str], current_process: str | None, question: str, answer: str
) -> TurnAnalysis:
    """Never raises: if the model fails, the turn counts as «nothing learned»."""
    prompt = get_prompts().render(
        "analyze_turn",
        processes=processes,
        current_process=current_process,
        aspects=[{"key": a.key, "label": a.label} for a in ASPECTS],
        question=question,
        answer=answer,
    )
    try:
        return await llm.complete_json([Message("user", prompt.text)], TurnAnalysis)
    except LLMError as exc:
        log.warning("analyze_turn failed: %s", exc)
        return TurnAnalysis()


def _clean_question(text: str) -> str:
    text = text.strip().strip('"«»').strip()
    for prefix in ("Вопрос:", "Интервьюер:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    return text


async def next_question(
    llm: LLMProvider, step: NextStep, *, process_name: str | None, turns: list[tuple[str, str]]
) -> tuple[str, bool]:
    """Returns (question, from_llm). Steps without LLM and LLM failures use fixed texts (D-041)."""
    fallback = fallback_question(step, process_name)
    if step.kind not in LLM_STEPS:
        return fallback, False
    aspect = BY_KEY.get(step.aspect or "")
    prompt = get_prompts().render(
        "interviewer_system",
        kind=step.kind.value,
        process_name=process_name or "",
        aspect_label=aspect.label if aspect else "",
        aspect_example=aspect.example if aspect else "",
        probe_type=step.probe_type,
        vague_reason=step.vague_reason,
        recent_turns=format_turns(turns),
    )
    try:
        question = _clean_question(
            await llm.complete([Message("user", prompt.text)], temperature=0.4, max_tokens=200)
        )
    except LLMError as exc:
        log.warning("question generation failed: %s", exc)
        return fallback, False
    return (question, True) if question else (fallback, False)
