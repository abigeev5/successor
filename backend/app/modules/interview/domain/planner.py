"""The deterministic interview planner (SPEC 7.4, step [3]). Pure functions, no I/O.

Each function takes a Snapshot (after the expert's answer was applied) and returns the next step
and the new session state. The LLM only phrases the question for the chosen step.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from app.modules.interview.domain.analysis import TurnAnalysis
from app.modules.interview.domain.aspects import BY_KEY, COVERAGE_TARGET, MAX_PROBE_STREAK, PRIORITY
from app.modules.interview.domain.state import InterviewState, Phase, Probe, Snapshot, coverage


class StepKind(StrEnum):
    INTRO = "intro"
    MAP_COLLECT = "map_collect"
    CONFIRM_PROCESSES = "confirm_processes"
    WALKTHROUGH = "walkthrough"
    PROBE = "probe"
    EXAMPLE_FOLLOWUP = "example_followup"
    WRAPUP = "wrapup"
    FINISH = "finish"


@dataclass(frozen=True)
class NextStep:
    kind: StepKind
    process_id: uuid.UUID | None = None
    aspect: str | None = None
    probe_type: str = "confirm"
    vague_reason: str | None = None


def _blocked(state: InterviewState, process_id: uuid.UUID | None, aspect: str | None) -> bool:
    last = state.last_probe
    return (
        last is not None
        and last.process_id == process_id
        and last.aspect == aspect
        and state.probe_streak >= MAX_PROBE_STREAK
    )


def _record(state: InterviewState, step: NextStep) -> InterviewState:
    last = state.last_probe
    same = last is not None and (last.process_id, last.aspect) == (step.process_id, step.aspect)
    return state.model_copy(
        update={
            "last_probe": Probe(process_id=step.process_id, aspect=step.aspect, kind=step.kind.value),
            "probe_streak": state.probe_streak + 1 if same else 1,
        }
    )


def _start_next_process(snapshot: Snapshot, state: InterviewState) -> tuple[NextStep, InterviewState]:
    """Next not-done process by criticality (desc), keeping the list order on ties; or wrap-up."""
    remaining = [p for p in snapshot.processes if p.id not in state.done_process_ids]
    remaining.sort(key=lambda p: -p.criticality)
    if not remaining:
        step = NextStep(StepKind.WRAPUP, probe_type="confirm")
        return step, _record(
            state.model_copy(update={"phase": Phase.WRAPUP, "current_process_id": None}), step
        )
    process = remaining[0]
    step = NextStep(StepKind.WALKTHROUGH, process_id=process.id, aspect="steps", probe_type="walkthrough")
    new_state = state.model_copy(update={"phase": Phase.WALKTHROUGH, "current_process_id": process.id})
    return step, _record(new_state, step)


def _finish_current(state: InterviewState) -> InterviewState:
    done = list(state.done_process_ids)
    if state.current_process_id is not None and state.current_process_id not in done:
        done.append(state.current_process_id)
    return state.model_copy(update={"done_process_ids": done, "current_process_id": None})


def _deepen(
    snapshot: Snapshot, state: InterviewState, analysis: TurnAnalysis
) -> tuple[NextStep, InterviewState]:
    current = state.current_process_id
    if current is None or snapshot.process(current) is None:
        return _start_next_process(snapshot, _finish_current(state))
    aspects = snapshot.aspects_of(current)

    last = state.last_probe
    if analysis.is_vague and last is not None and last.aspect and not _blocked(state, current, last.aspect):
        step = NextStep(
            StepKind.EXAMPLE_FOLLOWUP,
            process_id=current,
            aspect=last.aspect,
            probe_type="example_followup",
            vague_reason=analysis.vague_reason,
        )
        return step, _record(state.model_copy(update={"phase": Phase.DEEPEN}), step)

    if coverage(aspects) >= COVERAGE_TARGET:
        return _start_next_process(snapshot, _finish_current(state))

    for wanted in ("missing", "partial"):
        for key in PRIORITY:
            if (
                aspects[key].status == wanted
                and not aspects[key].not_applicable
                and not _blocked(state, current, key)
            ):
                step = NextStep(
                    StepKind.PROBE, process_id=current, aspect=key, probe_type=BY_KEY[key].probe_type
                )
                return step, _record(state.model_copy(update={"phase": Phase.DEEPEN}), step)
    # Everything left was asked twice in a row: move on.
    return _start_next_process(snapshot, _finish_current(state))


def _map(snapshot: Snapshot, state: InterviewState) -> tuple[NextStep, InterviewState]:
    state = state.model_copy(update={"phase": Phase.MAP})
    # Without any process the interview cannot go on, so confirmation is asked again and again.
    if state.candidates and (not snapshot.processes or not _blocked(state, None, "map_confirm")):
        step = NextStep(StepKind.CONFIRM_PROCESSES, aspect="map_confirm")
        return step, _record(state, step)
    if not snapshot.processes or state.map_questions == 0:
        step = NextStep(StepKind.MAP_COLLECT, aspect="map_collect", probe_type="cue")
        return step, _record(state.model_copy(update={"map_questions": state.map_questions + 1}), step)
    return _start_next_process(snapshot, state)


def first_step(snapshot: Snapshot, *, first_session: bool) -> tuple[NextStep, InterviewState]:
    """The opening question of a session."""
    state = snapshot.state
    if first_session:
        step = NextStep(StepKind.INTRO, probe_type="confirm")
        return step, _record(state.model_copy(update={"phase": Phase.INTRO}), step)
    # A later session continues with processes that are not covered yet.
    done = [p.id for p in snapshot.processes if coverage(snapshot.aspects_of(p.id)) >= COVERAGE_TARGET]
    return _start_next_process(snapshot, state.model_copy(update={"done_process_ids": done}))


def plan_next(snapshot: Snapshot, analysis: TurnAnalysis) -> tuple[NextStep, InterviewState]:
    """The step after the expert's answer (the snapshot already includes the analysis)."""
    state = snapshot.state
    if state.phase in (Phase.INTRO, Phase.MAP):
        return _map(snapshot, state)
    if state.phase in (Phase.WALKTHROUGH, Phase.DEEPEN):
        return _deepen(snapshot, state.model_copy(update={"phase": Phase.DEEPEN}), analysis)
    if state.phase is Phase.WRAPUP:
        step = NextStep(StepKind.FINISH)
        return step, state.model_copy(update={"phase": Phase.DONE})
    return NextStep(StepKind.FINISH), state


def after_processes_confirmed(snapshot: Snapshot) -> tuple[NextStep, InterviewState]:
    """The expert confirmed the duty map in the UI; candidates were cleared by the service."""
    state = snapshot.state.model_copy(update={"candidates": []})
    if state.phase in (Phase.INTRO, Phase.MAP) or state.current_process_id is None:
        return _start_next_process(snapshot, state)
    return _deepen(snapshot, state.model_copy(update={"phase": Phase.DEEPEN}), TurnAnalysis())


def skip_process(snapshot: Snapshot) -> tuple[NextStep, InterviewState]:
    """«Следующий процесс»."""
    return _start_next_process(snapshot, _finish_current(snapshot.state))
