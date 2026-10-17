"""When the assistant refuses (SPEC 7.8)."""

NO_ANSWER = "NO_ANSWER"


def refuse_before_llm(best_cosine: float | None, fts_hits: int, threshold: float) -> bool:
    """No relevant chunk by meaning and no full-text match → refuse without calling the LLM."""
    return fts_hits == 0 and (best_cosine is None or best_cosine < threshold)


def is_no_answer(text: str) -> bool:
    return text.strip().strip("\"'«»`").upper().startswith(NO_ANSWER)
