"""When the assistant refuses."""

NO_ANSWER = "NO_ANSWER"


def refuse_before_llm(
    best_cosine: float | None, text_coverage: float, min_similarity: float, min_coverage: float
) -> bool:
    """No relevant chunk by meaning and no full-text match → refuse without calling the LLM.

    A full-text match is a chunk with at least `min_coverage` of the question's words:
    any single shared word («студент», «отчёт») is not enough.
    """
    return text_coverage < min_coverage and (best_cosine is None or best_cosine < min_similarity)


def is_no_answer(text: str) -> bool:
    return text.strip().strip("\"'«»`").upper().startswith(NO_ANSWER)
