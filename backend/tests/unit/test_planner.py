"""plan_next and friends (vague, map, process switch, wrapup, repeat limit)."""

import uuid

from app.modules.interview.domain.analysis import TurnAnalysis
from app.modules.interview.domain.aspects import ASPECT_KEYS
from app.modules.interview.domain.planner import (
    StepKind,
    after_processes_confirmed,
    first_step,
    plan_next,
    skip_process,
)
from app.modules.interview.domain.state import (
    AspectState,
    InterviewState,
    Phase,
    Probe,
    ProcessCandidate,
    ProcessInfo,
    Snapshot,
)

RETAKES = ProcessInfo(id=uuid.uuid4(), name="Оформление пересдач", criticality=2)
REPORT = ProcessInfo(id=uuid.uuid4(), name="Отчёт о движении контингента", criticality=3)
NOTHING = TurnAnalysis()


def covered(*keys: str) -> dict[str, AspectState]:
    return {k: AspectState(status="covered") for k in keys}


def snap(
    state: InterviewState | None = None,
    processes: tuple[ProcessInfo, ...] = (RETAKES, REPORT),
    aspects: dict[uuid.UUID, dict[str, AspectState]] | None = None,
) -> Snapshot:
    return Snapshot(state or InterviewState(), list(processes), aspects or {})


def deepen_state(
    current: ProcessInfo, last_aspect: str = "steps", streak: int = 1, **kw: object
) -> InterviewState:
    return InterviewState(
        phase=Phase.DEEPEN,
        current_process_id=current.id,
        last_probe=Probe(process_id=current.id, aspect=last_aspect, kind="probe"),
        probe_streak=streak,
        **kw,  # type: ignore[arg-type]
    )


def test_first_session_starts_with_intro() -> None:
    step, state = first_step(snap(), first_session=True)
    assert step.kind is StepKind.INTRO
    assert state.phase is Phase.INTRO


def test_later_session_skips_covered_processes() -> None:
    eight = covered(*ASPECT_KEYS[:8])  # 8/11 ≈ 0.73 ≥ 0.7
    step, state = first_step(snap(aspects={REPORT.id: eight}), first_session=False)
    assert (step.kind, step.process_id) == (StepKind.WALKTHROUGH, RETAKES.id)
    assert REPORT.id in state.done_process_ids


def test_after_intro_asks_for_the_duty_map_once() -> None:
    step, state = plan_next(snap(InterviewState(phase=Phase.INTRO)), NOTHING)
    assert step.kind is StepKind.MAP_COLLECT
    assert (state.phase, state.map_questions) == (Phase.MAP, 1)


def test_candidates_are_confirmed_before_walkthrough() -> None:
    state = InterviewState(phase=Phase.MAP, map_questions=1, candidates=[ProcessCandidate(name="Справки")])
    step, _ = plan_next(snap(state), NOTHING)
    assert step.kind is StepKind.CONFIRM_PROCESSES


def test_map_done_starts_with_the_most_critical_process() -> None:
    step, state = plan_next(snap(InterviewState(phase=Phase.MAP, map_questions=1)), NOTHING)
    assert (step.kind, step.process_id, step.aspect) == (StepKind.WALKTHROUGH, REPORT.id, "steps")
    assert (state.phase, state.current_process_id) == (Phase.WALKTHROUGH, REPORT.id)


def test_without_processes_keeps_collecting_the_map() -> None:
    step, _ = plan_next(snap(InterviewState(phase=Phase.MAP, map_questions=1), processes=()), NOTHING)
    assert step.kind is StepKind.MAP_COLLECT


def test_confirm_asked_twice_is_not_repeated_when_processes_exist() -> None:
    state = InterviewState(
        phase=Phase.MAP,
        map_questions=1,
        candidates=[ProcessCandidate(name="Справки")],
        last_probe=Probe(process_id=None, aspect="map_confirm", kind="confirm_processes"),
        probe_streak=2,
    )
    assert plan_next(snap(state), NOTHING)[0].kind is StepKind.WALKTHROUGH
    # …but without any process confirmation is the only way forward.
    assert plan_next(snap(state, processes=()), NOTHING)[0].kind is StepKind.CONFIRM_PROCESSES


def test_confirmed_processes_start_the_walkthrough() -> None:
    state = InterviewState(phase=Phase.MAP, candidates=[ProcessCandidate(name="Справки")])
    step, new_state = after_processes_confirmed(snap(state))
    assert step.kind is StepKind.WALKTHROUGH
    assert new_state.candidates == []


def test_walkthrough_answer_leads_to_the_most_important_missing_aspect() -> None:
    state = InterviewState(phase=Phase.WALKTHROUGH, current_process_id=REPORT.id)
    step, new_state = plan_next(snap(state, aspects={REPORT.id: covered("steps")}), NOTHING)
    assert (step.kind, step.aspect, step.probe_type) == (StepKind.PROBE, "done_criteria", "cue")
    assert new_state.phase is Phase.DEEPEN


def test_vague_answer_asks_for_an_example_on_the_same_aspect() -> None:
    vague = TurnAnalysis(is_vague=True, vague_reason="нет конкретного случая")
    step, state = plan_next(snap(deepen_state(REPORT, "exceptions")), vague)
    assert (step.kind, step.aspect, step.vague_reason) == (
        StepKind.EXAMPLE_FOLLOWUP,
        "exceptions",
        "нет конкретного случая",
    )
    assert state.probe_streak == 2


def test_same_aspect_is_not_asked_more_than_twice_in_a_row() -> None:
    vague = TurnAnalysis(is_vague=True)
    state = deepen_state(REPORT, "done_criteria", streak=2)
    step, _ = plan_next(snap(state, aspects={REPORT.id: covered("steps")}), vague)
    assert (step.kind, step.aspect) == (StepKind.PROBE, "exceptions")


def test_not_applicable_aspects_are_skipped() -> None:
    aspects = {
        REPORT.id: {**covered("steps"), "done_criteria": AspectState(status="covered", not_applicable=True)}
    }
    step, _ = plan_next(snap(deepen_state(REPORT), aspects=aspects), NOTHING)
    assert step.aspect == "exceptions"


def test_partial_aspects_are_asked_after_missing_ones() -> None:
    aspects = {REPORT.id: {key: AspectState(status="covered") for key in ASPECT_KEYS[:6]}}
    aspects[REPORT.id]["exceptions"] = AspectState(status="partial")
    # covered 6 + partial 0.5 → 6.5/11 ≈ 0.59 < 0.7; missing: pitfalls, contacts, timing, rationale
    step, _ = plan_next(snap(deepen_state(REPORT), aspects=aspects), NOTHING)
    assert step.aspect == "pitfalls"


def test_covered_process_switches_to_the_next_one() -> None:
    step, state = plan_next(
        snap(deepen_state(REPORT), aspects={REPORT.id: covered(*ASPECT_KEYS[:8])}), NOTHING
    )
    assert (step.kind, step.process_id) == (StepKind.WALKTHROUGH, RETAKES.id)
    assert state.done_process_ids == [REPORT.id]


def test_last_covered_process_leads_to_wrapup_then_finish() -> None:
    state = deepen_state(RETAKES, done_process_ids=[REPORT.id])
    step, state = plan_next(snap(state, aspects={RETAKES.id: covered(*ASPECT_KEYS)}), NOTHING)
    assert step.kind is StepKind.WRAPUP and state.phase is Phase.WRAPUP
    step, state = plan_next(snap(state), NOTHING)
    assert step.kind is StepKind.FINISH and state.phase is Phase.DONE


def test_next_process_button() -> None:
    step, state = skip_process(snap(deepen_state(REPORT)))
    assert (step.kind, step.process_id) == (StepKind.WALKTHROUGH, RETAKES.id)
    assert REPORT.id in state.done_process_ids
