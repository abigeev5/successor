from app.modules.search.domain.chunking import chunk_card, split_blocks
from app.modules.search.domain.rrf import group_by_card, rrf


def test_split_blocks_keeps_steps_apart() -> None:
    body = "Вступление.\n\n1. Первый шаг\n2. Второй шаг\n- пункт"
    assert split_blocks(body) == ["Вступление.", "1. Первый шаг", "2. Второй шаг", "- пункт"]


def test_small_card_is_one_chunk_with_title_summary_and_condition() -> None:
    [chunk] = chunk_card("Срок отчёта", "До 5-го числа", "Сдавать в деканат.", applies_when="каждый месяц")
    assert chunk == "Срок отчёта\nДо 5-го числа\nКогда применять: каждый месяц\nСдавать в деканат."


def test_long_card_is_split_and_every_chunk_starts_with_title() -> None:
    body = "\n\n".join(f"{i}. " + "слово " * 30 for i in range(1, 11))
    chunks = chunk_card("Порядок", "Суть", body, max_chars=400)
    assert len(chunks) > 1
    assert all(c.startswith("Порядок\n") for c in chunks)
    assert "Суть" in chunks[0] and "Суть" not in chunks[1]
    assert all(f"{i}. " in "\n".join(chunks) for i in range(1, 11))  # nothing lost


def test_empty_body_still_gives_a_chunk() -> None:
    assert chunk_card("Заголовок", "", "") == ["Заголовок"]


def test_rrf_rewards_items_found_by_both_rankings() -> None:
    fused = rrf([["a", "b", "c"], ["c", "d"]])
    assert fused[0][0] == "c"
    assert dict(fused)["a"] == 1 / 61


def test_group_by_card_keeps_best_chunk_order_and_limit() -> None:
    card_of = {"c1": "A", "c2": "B", "c3": "A", "c4": "C"}
    assert group_by_card(["c1", "c2", "c3", "c4"], card_of, limit=2) == ["A", "B"]
    assert group_by_card(["c3", "c4", "c2"], card_of, limit=5) == ["A", "C", "B"]
