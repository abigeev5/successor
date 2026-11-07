import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.interview.domain.analysis import AspectTouch, NewProcess, TurnAnalysis, apply_analysis
from app.modules.interview.domain.aspects import ASPECT_KEYS, PRIORITY
from app.modules.interview.domain.state import (
    AspectState,
    InterviewState,
    ProcessCandidate,
    ProcessInfo,
    Snapshot,
    coverage,
)
from app.modules.interview.domain.timing import active_increment

RETAKES = ProcessInfo(id=uuid.uuid4(), name="Оформление пересдач", criticality=2)
REPORT = ProcessInfo(id=uuid.uuid4(), name="Отчёт о движении контингента", criticality=3)


def snap(current: uuid.UUID | None = None, **aspects: dict[str, AspectState]) -> Snapshot:
    return Snapshot(
        InterviewState(current_process_id=current),
        [RETAKES, REPORT],
        {uuid.UUID(k): v for k, v in aspects.items()},
    )


def touch(aspect: str, status: str, process: str | None = None) -> TurnAnalysis:
    return TurnAnalysis(aspects_touched=[AspectTouch(process_name=process, aspect=aspect, status=status)])  # type: ignore[arg-type]


def test_priority_lists_every_aspect_once() -> None:
    assert sorted(PRIORITY) == sorted(ASPECT_KEYS) and len(ASPECT_KEYS) == 11


def test_coverage_formula() -> None:
    assert coverage({}) == 0
    aspects = {"steps": AspectState(status="covered"), "tools": AspectState(status="partial")}
    assert coverage(aspects) == pytest.approx(1.5 / 11)
    na = {"timing": AspectState(status="covered", not_applicable=True)}
    assert coverage(na) == pytest.approx(1 / 11)


def test_aspect_of_named_process_is_updated_by_fuzzy_name() -> None:
    result, changed = apply_analysis(snap(), touch("steps", "covered", "пересдачи"))
    assert result.aspects_of(RETAKES.id)["steps"].status == "covered"
    assert changed == {(RETAKES.id, "steps")}


def test_unnamed_aspect_goes_to_the_current_process() -> None:
    _, changed = apply_analysis(snap(current=REPORT.id), touch("timing", "partial"))
    assert changed == {(REPORT.id, "timing")}
    # Without a current process there is nowhere to put it.
    assert apply_analysis(snap(), touch("timing", "partial"))[1] == set()


def test_statuses_never_go_down() -> None:
    base = snap(**{str(RETAKES.id): {"steps": AspectState(status="covered")}})
    result, changed = apply_analysis(base, touch("steps", "partial", RETAKES.name))
    assert result.aspects_of(RETAKES.id)["steps"].status == "covered" and changed == set()


def test_not_applicable_marks_covered_with_flag() -> None:
    result, _ = apply_analysis(snap(current=REPORT.id), touch("exceptions", "not_applicable"))
    assert result.aspects_of(REPORT.id)["exceptions"] == AspectState(status="covered", not_applicable=True)


def test_unknown_aspect_is_ignored_and_input_is_not_mutated() -> None:
    base = snap(current=REPORT.id)
    _, changed = apply_analysis(base, touch("salary", "covered"))
    assert changed == set()
    apply_analysis(base, touch("steps", "covered"))
    assert base.aspects == {}


def test_new_processes_become_candidates_without_duplicates() -> None:
    base = snap()
    base.state.candidates.append(ProcessCandidate(name="Справки для военкомата"))
    analysis = TurnAnalysis(
        new_processes=[
            NewProcess(name="Отчет о движении контингента"),  # already a process (ё/е)
            NewProcess(name="справки для военкомата"),  # already a candidate
            NewProcess(name="Подготовка экзаменационных ведомостей", description="перед сессией"),
        ]
    )
    result, _ = apply_analysis(base, analysis)
    assert [c.name for c in result.state.candidates] == [
        "Справки для военкомата",
        "Подготовка экзаменационных ведомостей",
    ]


def test_active_time_ignores_long_pauses() -> None:
    now = datetime.now(UTC)
    assert active_increment(None, now) == 0
    assert active_increment(now - timedelta(seconds=90), now) == 90
    assert active_increment(now - timedelta(minutes=6), now) == 0
