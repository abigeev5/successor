"""Interview → duty map → walkthrough → probes → finish → extraction job → drafts with real quotes."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.jobs import Job, JobContext
from app.modules.analytics.models import ProductEvent
from app.modules.identity.models import UserRole
from app.modules.interview.handlers import EXTRACT_JOB, extract_cards_from_session
from app.modules.interview.models import InterviewSession
from app.modules.knowledge.domain.quotes import find_quote
from app.modules.knowledge.models import CardSource, KnowledgeCard
from app.modules.org.models import Process
from tests.factories import give_consent, login, make_handover, make_org_unit, make_process, make_user

INTRO_ANSWER = (
    "Я специалист учебного отдела: оформляю пересдачи и раз в месяц делаю отчёт о движении контингента."
)
WALKTHROUGH_ANSWER = (
    "В последний раз я выгрузила список приказов из портала, сверила численность с деканатами "
    "и отправила отчёт в отдел статистики до пятого числа."
)
VAGUE_ANSWER = "По ситуации, как обычно."
DONE_ANSWER = (
    "Отчёт готов, когда численность сходится с данными деканатов до человека. "
    "Если не сходится — звоню секретарю деканата."
)


def analysis(answer: str, **data: Any) -> dict[str, Any]:
    return {"match": f"Ответ сотрудника: {answer[:40]}", "response_json": data}


def covered(*aspects: str) -> list[dict[str, Any]]:
    return [{"process_name": None, "aspect": a, "status": "covered"} for a in aspects]


def script_llm(app: FastAPI) -> Any:
    llm = app.state.providers.llm
    from app.providers.llm.fake import FakeRule

    rules = [
        analysis(
            INTRO_ANSWER,
            new_processes=[{"name": "Отчёт о движении контингента", "description": "ежемесячно"}],
        ),
        analysis(WALKTHROUGH_ANSWER, aspects_touched=covered("steps", "tools", "inputs", "timing")),
        analysis(VAGUE_ANSWER, is_vague=True, vague_reason="нет конкретного случая"),
        analysis(DONE_ANSWER, aspects_touched=covered("done_criteria", "exceptions", "pitfalls", "contacts")),
        {"match": "Ты — интервьюер", "response": "Расскажите, как это было в последний раз?"},
        {
            "match": "Ты извлекаешь из интервью карточки",
            "response_json": {
                "cards": [
                    {
                        "type": "procedure",
                        "process_name": "отчет по контингенту",
                        "title": "Как сдать отчёт о движении контингента",
                        "summary": "Выгрузить приказы, сверить с деканатами, отправить до 5-го.",
                        "body_md": "1. Выгрузить приказы\n2. Сверить\n3. Отправить",
                        "quotes": [{"fragment": 2, "text": "выгрузила список приказов из портала"}],
                    },
                    {
                        "type": "rule",
                        "process_name": None,
                        "title": "Когда отчёт можно отправлять",
                        "summary": "Численность сходится с деканатами до человека.",
                        "body_md": "Сверить численность с деканатами.",
                        "quotes": [{"fragment": 4, "text": "численность сходится с данными деканатов"}],
                    },
                    {
                        "type": "rule",
                        "title": "Отчёт отдаётся ректору лично",
                        "summary": "Выдумка модели.",
                        "quotes": [{"fragment": 2, "text": "отправляю отчёт ректору лично в руки"}],
                    },
                    {
                        "type": "procedure",
                        "process_name": "отчет по контингенту",
                        "title": "Как сдать отчёт о движении контингента",
                        "summary": "Выгрузить приказы, сверить с деканатами, отправить до 5-го.",
                        "quotes": [{"fragment": 2, "text": "сверила численность с деканатами"}],
                    },
                ]
            },
        },
    ]
    llm.rules = [FakeRule.from_dict(rule) for rule in rules]
    return llm


@pytest.fixture
async def setup(db: AsyncSession) -> dict[str, Any]:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    retakes = await make_process(db, unit, "Оформление пересдач", criticality=2)
    handover = await make_handover(
        db, org_unit=unit, manager=manager, expert=expert, successor=successor, processes=[retakes]
    )
    await give_consent(db, expert, handover)
    await db.commit()
    return {
        "handover": handover,
        "expert": expert,
        "successor": successor,
        "manager": manager,
        "retakes": retakes,
    }


async def test_full_interview_and_extraction(
    app: FastAPI, client: httpx.AsyncClient, db: AsyncSession, setup: dict[str, Any]
) -> None:
    script_llm(app)
    handover = setup["handover"]
    await login(client, setup["expert"])

    # Start: the intro is a fixed text with the expert's and successor's names.
    session = (await client.post("/api/interviews", json={"handover_id": str(handover.id)})).json()
    sid = session["id"]
    assert session["phase"] == "intro"
    assert setup["expert"].full_name in session["messages"][0]["content"]
    assert setup["successor"].full_name in session["messages"][0]["content"]
    # Starting again returns the same unfinished session.
    assert (await client.post("/api/interviews", json={"handover_id": str(handover.id)})).json()["id"] == sid

    # Intro answer → a new process candidate → the duty map must be confirmed.
    session = (await client.post(f"/api/interviews/{sid}/messages", json={"text": INTRO_ANSWER})).json()
    assert [c["name"] for c in session["candidates"]] == ["Отчёт о движении контингента"]
    assert session["messages"][-1]["meta"]["kind"] == "confirm_processes"

    session = (
        await client.post(
            f"/api/interviews/{sid}/confirm-processes",
            json={
                "items": [{"name": "Отчёт о движении контингента", "frequency": "monthly", "criticality": 3}]
            },
        )
    ).json()
    assert session["candidates"] == []
    report_id = (
        await db.execute(select(Process.id).where(Process.name == "Отчёт о движении контингента"))
    ).scalar_one()
    last = session["messages"][-1]
    assert last["meta"] == {**last["meta"], "kind": "walkthrough", "process_id": str(report_id), "llm": True}
    assert session["current_process_id"] == str(report_id)  # the most critical one first

    # Walkthrough answer covers 4 aspects → probe for the next priority aspect.
    session = (await client.post(f"/api/interviews/{sid}/messages", json={"text": WALKTHROUGH_ANSWER})).json()
    assert session["messages"][-1]["meta"]["aspect"] == "done_criteria"

    # A vague answer → ask for an example about the same aspect.
    session = (await client.post(f"/api/interviews/{sid}/messages", json={"text": VAGUE_ANSWER})).json()
    assert session["messages"][-1]["meta"]["kind"] == "example_followup"

    # 8 of 11 aspects ≥ 70 % → next process.
    session = (await client.post(f"/api/interviews/{sid}/messages", json={"text": DONE_ANSWER})).json()
    assert session["messages"][-1]["meta"]["kind"] == "walkthrough"
    assert session["current_process_id"] == str(setup["retakes"].id)
    coverage = {c["name"]: c["coverage"] for c in session["coverage"]}
    assert coverage == {
        "Отчёт о движении контингента": pytest.approx(8 / 11, abs=1e-3),
        "Оформление пересдач": 0,
    }

    # Pause / resume / finish.
    assert (await client.post(f"/api/interviews/{sid}/pause")).json()["status"] == "paused"
    assert (await client.post(f"/api/interviews/{sid}/resume")).json()["status"] == "active"
    finished = (await client.post(f"/api/interviews/{sid}/finish")).json()
    assert finished["status"] == "finished"
    assert (await client.post(f"/api/interviews/{sid}/messages", json={"text": "ещё"})).status_code == 409

    # Finishing queued exactly one extraction job; the worker runs it.
    [job] = (await db.execute(select(Job))).scalars().all()
    job_id = job.id
    assert (job.type, job.payload) == (EXTRACT_JOB, {"session_id": sid})
    assert await jobs.run_one(get_sessionmaker(), get_settings(), app.state.providers)
    db.expire_all()
    assert (await db.get(Job, job_id)).status.value == "done"  # type: ignore[union-attr]

    cards = list((await db.execute(select(KnowledgeCard).order_by(KnowledgeCard.created_at))).scalars())
    assert [(c.title, c.status.value) for c in cards] == [
        ("Как сдать отчёт о движении контингента", "draft"),
        ("Когда отчёт можно отправлять", "draft"),
    ]
    assert cards[0].process_id == report_id  # «отчет по контингенту» matched despite inflection
    assert cards[1].process_id is None

    sources = list((await db.execute(select(CardSource).order_by(CardSource.created_at))).scalars())
    by_card = {c.id: [s.quote for s in sources if s.card_id == c.id] for c in cards}
    # The duplicate card was merged into the first draft as a second source.
    assert by_card[cards[0].id] == [
        "выгрузила список приказов из портала",
        "сверила численность с деканатами",
    ]
    # Every stored quote really occurs in the interview.
    answers = [WALKTHROUGH_ANSWER, DONE_ANSWER]
    assert all(any(find_quote(s.quote, a) for a in answers) for s in sources)

    events = dict(
        (await db.execute(select(ProductEvent.name, func.count()).group_by(ProductEvent.name))).all()
    )
    assert events == {
        "interview_turn": 4,
        "interview_session_finished": 1,
        "card_generated": 2,
        "card_dropped_no_evidence": 1,
    }

    # Running the job again does nothing (idempotent, D-043).
    async with get_sessionmaker()() as other:
        await extract_cards_from_session(
            JobContext(db=other, settings=get_settings(), providers=app.state.providers), {"session_id": sid}
        )
        await other.commit()
    assert await db.scalar(select(func.count()).select_from(KnowledgeCard)) == 2
    assert (await db.get(InterviewSession, sid)).extracted_at is not None  # type: ignore[union-attr]


async def test_transcript_access(client: httpx.AsyncClient, db: AsyncSession, setup: dict[str, Any]) -> None:
    await login(client, setup["expert"])
    sid = (await client.post("/api/interviews", json={"handover_id": str(setup["handover"].id)})).json()["id"]

    await login(client, setup["successor"])
    assert (await client.get(f"/api/interviews/{sid}")).status_code == 403  # no raw transcripts (SPEC 7.1)
    coverage = await client.get("/api/interviews/coverage", params={"handover_id": str(setup["handover"].id)})
    assert coverage.status_code == 200

    await login(client, setup["manager"])
    assert (await client.post(f"/api/interviews/{sid}/messages", json={"text": "x"})).status_code == 403
    sessions = (await client.get("/api/interviews", params={"handover_id": str(setup["handover"].id)})).json()
    assert [(s["id"], s["messages_count"]) for s in sessions] == [(sid, 1)]


async def test_llm_failure_falls_back_to_fixed_questions(
    app: FastAPI, client: httpx.AsyncClient, db: AsyncSession, setup: dict[str, Any]
) -> None:
    from app.providers.llm.base import LLMError

    class BrokenLLM:
        name = model = "broken"

        async def complete(self, *a: Any, **k: Any) -> str:
            raise LLMError("down")

        async def complete_json(self, *a: Any, **k: Any) -> Any:
            raise LLMError("down")

    app.state.providers.llm = BrokenLLM()
    await login(client, setup["expert"])
    sid = (await client.post("/api/interviews", json={"handover_id": str(setup["handover"].id)})).json()["id"]
    await client.post(f"/api/interviews/{sid}/messages", json={"text": "Оформляю пересдачи."})
    session = (await client.post(f"/api/interviews/{sid}/next-process")).json()
    last = session["messages"][-1]
    assert last["meta"]["kind"] in ("walkthrough", "wrapup") and last["meta"]["llm"] is False
    assert last["content"]
