"""Interview sessions (SPEC 7.4). One turn = analyze_turn (LLM) → update coverage → plan_next (code)
→ next question (LLM). Session rows are locked during a turn, so parallel requests do not interleave."""

import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.events import bus
from app.core.prompts import get_prompts
from app.core.storage import Asset, AssetKind, absolute_path, save_bytes
from app.modules.handovers import service as handovers
from app.modules.handovers.access import HandoverRole, ensure_handover_access
from app.modules.handovers.models import MemberRole
from app.modules.identity.models import User
from app.modules.interview import llm
from app.modules.interview.domain.analysis import apply_analysis
from app.modules.interview.domain.aspects import ASPECTS
from app.modules.interview.domain.fallback import FINISH
from app.modules.interview.domain.planner import (
    NextStep,
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
    ProcessInfo,
    Snapshot,
    coverage,
)
from app.modules.interview.domain.timing import active_increment
from app.modules.interview.events import InterviewSessionFinished, InterviewTurnCompleted
from app.modules.interview.models import (
    InterviewMessage,
    InterviewSession,
    MessageRole,
    ProcessAspect,
    SessionStatus,
)
from app.modules.interview.schemas import (
    AspectOut,
    AudioOut,
    CandidateDecision,
    MessageOut,
    ProcessCoverageOut,
    SessionBrief,
    SessionOut,
)
from app.modules.org import service as org
from app.modules.org.domain.matching import match_name
from app.modules.privacy.service import require_consent
from app.providers.asr.base import Transcript
from app.providers.registry import Providers

MAX_AUDIO_MS = 2 * 60 * 1000  # D-036
MAX_AUDIO_BYTES = 20 * 1024 * 1024
TRANSCRIPT_READERS = [HandoverRole.EXPERT, HandoverRole.ADMIN]


def _now() -> datetime:
    return datetime.now(UTC)


# --- loading -------------------------------------------------------------------------------------


async def _snapshot(db: AsyncSession, handover_id: uuid.UUID, state: InterviewState) -> Snapshot:
    processes = await handovers.list_processes(db, handover_id)
    rows = (await db.execute(select(ProcessAspect).where(ProcessAspect.handover_id == handover_id))).scalars()
    aspects: dict[uuid.UUID, dict[str, AspectState]] = defaultdict(dict)
    for row in rows:
        aspects[row.process_id][row.aspect] = AspectState.model_validate(
            {"status": row.status, "not_applicable": row.not_applicable}
        )
    return Snapshot(
        state=state,
        processes=[ProcessInfo(id=p.id, name=p.name, criticality=p.criticality) for p in processes],
        aspects=dict(aspects),
    )


async def _lock(db: AsyncSession, session_id: uuid.UUID) -> InterviewSession:
    session = (
        await db.execute(select(InterviewSession).where(InterviewSession.id == session_id).with_for_update())
    ).scalar_one_or_none()
    if session is None:
        raise NotFound("Сессия интервью не найдена", code="session_not_found")
    return session


async def _own_session(db: AsyncSession, user: User, session_id: uuid.UUID) -> InterviewSession:
    """Locks a session the user may write to: the expert of the handover, with consent, not finished."""
    session = await _lock(db, session_id)
    await ensure_handover_access(db, user, session.handover_id, [HandoverRole.EXPERT])
    if session.expert_id != user.id:
        raise Forbidden("Это интервью другого сотрудника", code="not_your_session")
    if session.status is SessionStatus.FINISHED:
        raise Conflict("Сессия уже завершена. Начните новую.", code="session_finished")
    await require_consent(db, user.id, session.handover_id)
    return session


async def _messages(db: AsyncSession, session_id: uuid.UUID) -> list[InterviewMessage]:
    stmt = (
        select(InterviewMessage)
        .where(InterviewMessage.session_id == session_id)
        .order_by(InterviewMessage.seq)
    )
    return list((await db.execute(stmt)).scalars())


# --- writing ---------------------------------------------------------------------------------------


async def _add_message(
    db: AsyncSession,
    session: InterviewSession,
    role: MessageRole,
    content: str,
    meta: dict[str, object],
    audio_asset_id: uuid.UUID | None = None,
) -> InterviewMessage:
    last = await db.scalar(
        select(func.max(InterviewMessage.seq)).where(InterviewMessage.session_id == session.id)
    )
    message = InterviewMessage(
        session_id=session.id,
        seq=(last or 0) + 1,
        role=role,
        content=content,
        meta=meta,
        audio_asset_id=audio_asset_id,
    )
    db.add(message)
    await db.flush()
    return message


async def _intro_text(db: AsyncSession, session: InterviewSession, expert: User) -> str:
    successors = await handovers.member_ids(db, session.handover_id, MemberRole.SUCCESSOR)
    successor = await db.get(User, successors[0]) if successors else None
    return (
        get_prompts()
        .render(
            "interview_intro",
            expert_name=expert.full_name,
            successor_name=successor.full_name if successor else None,
        )
        .text
    )


async def _ask(
    db: AsyncSession,
    providers: Providers,
    session: InterviewSession,
    snapshot: Snapshot,
    step: NextStep,
    state: InterviewState,
    expert: User,
) -> InterviewMessage:
    """Phrases the step as a question, stores it and the new state."""
    process = snapshot.process(step.process_id)
    if step.kind is StepKind.INTRO:
        text, from_llm = await _intro_text(db, session, expert), False
    else:
        turns = [(m.role.value, m.content) for m in await _messages(db, session.id)]
        text, from_llm = await llm.next_question(
            providers.llm, step, process_name=process.name if process else None, turns=turns
        )
    session.state_json = state.model_dump(mode="json")
    session.phase = state.phase.value
    return await _add_message(
        db,
        session,
        MessageRole.INTERVIEWER,
        text,
        {
            "kind": step.kind.value,
            "process_id": str(step.process_id) if step.process_id else None,
            "aspect": step.aspect,
            "probe_type": step.probe_type,
            "llm": from_llm,
        },
    )


async def _save_aspects(
    db: AsyncSession, handover_id: uuid.UUID, snapshot: Snapshot, changed: set[tuple[uuid.UUID, str]]
) -> None:
    for process_id, aspect in changed:
        value = snapshot.aspects[process_id][aspect]
        stmt = insert(ProcessAspect).values(
            handover_id=handover_id,
            process_id=process_id,
            aspect=aspect,
            status=value.status,
            not_applicable=value.not_applicable,
        )
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["handover_id", "process_id", "aspect"],
                set_={
                    "status": value.status,
                    "not_applicable": value.not_applicable,
                    "updated_at": func.now(),
                },
            )
        )


async def _finish(db: AsyncSession, session: InterviewSession, user: User) -> None:
    session.status = SessionStatus.FINISHED
    session.finished_at = _now()
    session.phase = Phase.DONE.value
    await bus.publish(
        db,
        InterviewSessionFinished(
            session_id=session.id,
            handover_id=session.handover_id,
            user_id=user.id,
            active_seconds=session.active_seconds,
        ),
    )


def _touch(session: InterviewSession) -> None:
    now = _now()
    session.active_seconds += active_increment(session.last_activity_at, now)
    session.last_activity_at = now


# --- use cases ---------------------------------------------------------------------------------------


async def start(
    db: AsyncSession, providers: Providers, user: User, handover_id: uuid.UUID
) -> InterviewSession:
    """Opens a new session, or returns the unfinished one (one at a time per expert and handover)."""
    await ensure_handover_access(db, user, handover_id, [HandoverRole.EXPERT])
    await require_consent(db, user.id, handover_id)
    unfinished = (
        await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.handover_id == handover_id,
                InterviewSession.expert_id == user.id,
                InterviewSession.status != SessionStatus.FINISHED,
            )
            .order_by(InterviewSession.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if unfinished is not None:
        return unfinished

    first_session = not await db.scalar(
        select(func.count()).select_from(InterviewSession).where(InterviewSession.handover_id == handover_id)
    )
    session = InterviewSession(
        handover_id=handover_id,
        expert_id=user.id,
        state_json=InterviewState().model_dump(mode="json"),
        last_activity_at=_now(),
    )
    db.add(session)
    await db.flush()
    snapshot = await _snapshot(db, handover_id, InterviewState())
    step, state = first_step(snapshot, first_session=first_session)
    snapshot.state = state
    await _ask(db, providers, session, snapshot, step, state, user)
    await db.commit()
    return session


async def post_message(
    db: AsyncSession,
    providers: Providers,
    user: User,
    session_id: uuid.UUID,
    text: str,
    audio_asset_id: uuid.UUID | None = None,
) -> InterviewSession:
    session = await _own_session(db, user, session_id)
    session.status = SessionStatus.ACTIVE  # answering resumes a paused session
    if audio_asset_id is not None:
        asset = await db.get(Asset, audio_asset_id)
        if asset is None or asset.handover_id != session.handover_id or asset.owner_id != user.id:
            raise AppError("Аудиозапись не найдена", code="audio_not_found")

    state = InterviewState.model_validate(session.state_json)
    snapshot = await _snapshot(db, session.handover_id, state)
    history = await _messages(db, session.id)
    question = next((m.content for m in reversed(history) if m.role is MessageRole.INTERVIEWER), "")
    current = snapshot.process(state.current_process_id)
    await _add_message(
        db,
        session,
        MessageRole.EXPERT,
        text.strip(),
        {"phase": state.phase.value, "process_id": str(current.id) if current else None},
        audio_asset_id,
    )

    analysis = await llm.analyze_turn(
        providers.llm,
        processes=[p.name for p in snapshot.processes],
        current_process=current.name if current else None,
        question=question,
        answer=text,
    )
    updated, changed = apply_analysis(snapshot, analysis)
    step, new_state = plan_next(updated, analysis)
    updated.state = new_state
    await _ask(db, providers, session, updated, step, new_state, user)
    await _save_aspects(db, session.handover_id, updated, changed)
    _touch(session)
    await bus.publish(
        db,
        InterviewTurnCompleted(
            session_id=session.id,
            handover_id=session.handover_id,
            user_id=user.id,
            step=step.kind.value,
            voice=audio_asset_id is not None,
        ),
    )
    if step.kind is StepKind.FINISH:
        await _finish(db, session, user)
    await db.commit()
    return session


async def confirm_processes(
    db: AsyncSession, providers: Providers, user: User, session_id: uuid.UUID, items: list[CandidateDecision]
) -> InterviewSession:
    """The duty map (phase map): chosen candidates become processes of the handover (SPEC 7.4)."""
    session = await _own_session(db, user, session_id)
    handover = await handovers.get_handover(db, session.handover_id)
    unit_processes = [(p.id, p.name) for p in await org.list_processes(db, handover.org_unit_id)]
    chosen: list[uuid.UUID] = []
    for item in items:
        if not item.include:
            continue
        process_id = match_name(item.name, unit_processes)
        if process_id is None:
            process = await org.create_process(
                db,
                org_unit_id=handover.org_unit_id,
                name=item.name,
                description=item.description,
                frequency=item.frequency,
                criticality=item.criticality,
                created_by=user.id,
            )
            process_id = process.id
            unit_processes.append((process.id, process.name))
        chosen.append(process_id)
    if chosen:
        await handovers.link_processes(db, handover, chosen)

    state = InterviewState.model_validate(session.state_json).model_copy(update={"candidates": []})
    snapshot = await _snapshot(db, session.handover_id, state)
    step, new_state = after_processes_confirmed(snapshot)
    snapshot.state = new_state
    await _ask(db, providers, session, snapshot, step, new_state, user)
    _touch(session)
    await db.commit()
    return session


async def next_process(
    db: AsyncSession, providers: Providers, user: User, session_id: uuid.UUID
) -> InterviewSession:
    session = await _own_session(db, user, session_id)
    snapshot = await _snapshot(db, session.handover_id, InterviewState.model_validate(session.state_json))
    step, state = skip_process(snapshot)
    snapshot.state = state
    await _ask(db, providers, session, snapshot, step, state, user)
    await db.commit()
    return session


async def set_paused(db: AsyncSession, user: User, session_id: uuid.UUID, paused: bool) -> InterviewSession:
    session = await _own_session(db, user, session_id)
    session.status = SessionStatus.PAUSED if paused else SessionStatus.ACTIVE
    if not paused:
        session.last_activity_at = _now()  # the pause does not count as active time
    await db.commit()
    return session


async def finish(db: AsyncSession, user: User, session_id: uuid.UUID) -> InterviewSession:
    session = await _own_session(db, user, session_id)
    await _add_message(db, session, MessageRole.INTERVIEWER, FINISH, {"kind": StepKind.FINISH.value})
    await _finish(db, session, user)
    await db.commit()
    return session


async def transcribe_audio(
    db: AsyncSession, settings: Settings, providers: Providers, user: User, session_id: uuid.UUID, data: bytes
) -> AudioOut:
    """Voice answer (SPEC 7.4): store the audio, recognize it; the expert edits the text and sends it."""
    session = await _own_session(db, user, session_id)
    return await recognize_audio(db, settings, providers, user, session.handover_id, data)


async def recognize_audio(
    db: AsyncSession,
    settings: Settings,
    providers: Providers,
    user: User,
    handover_id: uuid.UUID,
    data: bytes,
) -> AudioOut:
    """Stores a voice answer (≤ 2 min) and recognizes it. Access and consent are checked by the caller."""
    asset = await save_bytes(
        db,
        settings,
        data,
        expected_kind=AssetKind.AUDIO,
        max_bytes=MAX_AUDIO_BYTES,
        owner_id=user.id,
        handover_id=handover_id,
    )
    path = absolute_path(settings, asset)
    await db.commit()  # release the session lock while the recognizer works
    try:
        transcript: Transcript = await asyncio.to_thread(providers.asr.transcribe, path, "ru")
    except Exception as exc:
        raise AppError(
            "Не удалось распознать речь. Попробуйте ещё раз или введите текст.",
            code="asr_failed",
            status_code=502,
        ) from exc
    if transcript.duration_ms is not None and transcript.duration_ms > MAX_AUDIO_MS:
        path.unlink(missing_ok=True)
        await db.delete(asset)
        await db.commit()
        raise AppError(
            "Запись длиннее 2 минут. Разбейте ответ на части.", code="audio_too_long", status_code=413
        )
    asset.duration_ms = transcript.duration_ms
    await db.commit()
    return AudioOut(asset_id=asset.id, text=transcript.text, duration_ms=transcript.duration_ms)


# --- reading -------------------------------------------------------------------------------------------


def coverage_view(snapshot: Snapshot) -> list[ProcessCoverageOut]:
    result = []
    for process in snapshot.processes:
        aspects = snapshot.aspects_of(process.id)
        result.append(
            ProcessCoverageOut(
                process_id=process.id,
                name=process.name,
                criticality=process.criticality,
                coverage=round(coverage(aspects), 3),
                aspects=[
                    AspectOut(
                        key=a.key,
                        label=a.label,
                        status=aspects[a.key].status,
                        not_applicable=aspects[a.key].not_applicable,
                    )
                    for a in ASPECTS
                ],
            )
        )
    return result


async def handover_coverage(db: AsyncSession, handover_id: uuid.UUID) -> list[ProcessCoverageOut]:
    return coverage_view(await _snapshot(db, handover_id, InterviewState()))


async def session_view(db: AsyncSession, user: User, session_id: uuid.UUID) -> SessionOut:
    session = await db.get(InterviewSession, session_id)
    if session is None:
        raise NotFound("Сессия интервью не найдена", code="session_not_found")
    await ensure_handover_access(db, user, session.handover_id, TRANSCRIPT_READERS)
    state = InterviewState.model_validate(session.state_json)
    messages = await _messages(db, session.id)
    return SessionOut(
        id=session.id,
        handover_id=session.handover_id,
        status=session.status,
        phase=session.phase,
        started_at=session.started_at,
        finished_at=session.finished_at,
        active_seconds=session.active_seconds,
        messages_count=len(messages),
        current_process_id=state.current_process_id,
        candidates=state.candidates,
        messages=[
            MessageOut.model_validate(m).model_copy(update={"has_audio": m.audio_asset_id is not None})
            for m in messages
        ],
        coverage=coverage_view(await _snapshot(db, session.handover_id, state)),
    )


async def list_sessions(db: AsyncSession, handover_id: uuid.UUID) -> list[SessionBrief]:
    counts = (
        select(InterviewMessage.session_id, func.count().label("n"))
        .group_by(InterviewMessage.session_id)
        .subquery()
    )
    rows = await db.execute(
        select(InterviewSession, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.session_id == InterviewSession.id)
        .where(InterviewSession.handover_id == handover_id)
        .order_by(InterviewSession.started_at.desc())
    )
    return [
        SessionBrief(
            id=s.id,
            handover_id=s.handover_id,
            status=s.status,
            phase=s.phase,
            started_at=s.started_at,
            finished_at=s.finished_at,
            active_seconds=s.active_seconds,
            messages_count=n,
        )
        for s, n in rows
    ]
