"""Metrics export: the order and Russian names of the CSV rows. Pure."""

from collections.abc import Mapping
from typing import Any, Literal

Kind = Literal["number", "share"]

# (field of MetricsOut, row name, kind)
CSV_ROWS: tuple[tuple[str, str, Kind], ...] = (
    ("expert_minutes", "Время эксперта, мин (интервью + записи + проверка)", "number"),
    ("interview_minutes", "Интервью, мин", "number"),
    ("recording_minutes", "Записи экрана, мин", "number"),
    ("review_minutes", "Проверка карточек, мин", "number"),
    ("interview_turns", "Ходов интервью", "number"),
    ("recordings_processed", "Обработано записей экрана", "number"),
    ("cards_generated", "Сгенерировано черновиков", "number"),
    ("cards_dropped_no_evidence", "Отброшено черновиков без цитаты", "number"),
    ("cards_approved", "Подтверждено карточек", "number"),
    ("cards_approved_edited", "Из них с правками", "number"),
    ("cards_rejected", "Отклонено карточек", "number"),
    ("approved_share", "Доля подтверждённых из сгенерированных, %", "share"),
    ("questions", "Вопросов ассистенту", "number"),
    ("answered_share", "Доля ответов, %", "share"),
    ("partial_share", "Доля частичных ответов, %", "share"),
    ("refused_share", "Доля отказов, %", "share"),
    ("helpful_share", "Доля оценок «помогло», %", "share"),
    ("feedback_count", "Оценок ответов", "number"),
    ("answer_latency_p95_ms", "Задержка ответа p95, мс", "number"),
    ("gaps_created", "Пробелов создано", "number"),
    ("gaps_answered", "Пробелов закрыто ответом", "number"),
    ("gaps_open_now", "Открытых пробелов сейчас", "number"),
    ("key_processes_coverage", "Покрытие ключевых процессов подтверждёнными карточками, %", "share"),
)


def share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def format_value(value: Any, kind: Kind) -> str:
    """Numbers as is; shares as percent with a comma (Excel in Russian locale); nothing → empty."""
    if value is None:
        return ""
    if kind == "share":
        return f"{value * 100:.1f}".replace(".", ",")
    return str(value)


def csv_rows(metrics: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [(name, format_value(metrics[field], kind)) for field, name, kind in CSV_ROWS]
