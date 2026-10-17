"""Assistant (SPEC 7.8): index → hybrid search → answer with citations → verification; refusal → gap."""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.modules.analytics.models import ProductEvent
from app.modules.assistant.models import QaLog
from app.modules.gaps.models import Gap
from app.modules.identity.models import UserRole
from app.modules.interview.models import InterviewMessage, InterviewSession, MessageRole
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardSource, CardStatus, KnowledgeCard
from app.modules.search.indexer import index_card
from app.modules.search.models import CardChunk
from app.providers.llm.base import LLMError, Message
from app.providers.llm.fake import FakeLLM, FakeRule
from tests.factories import give_consent, login, make_handover, make_org_unit, make_user
from tests.integration.test_voice import WEBM_AUDIO, StubASR

ANSWER_PROMPT = "Ты — ассистент преемника"
VERIFY_PROMPT = "Проверь, подтверждается ли"
QUESTION = "До какого числа сдавать отчёт о движении контингента?"
UNRELATED = "Как заказать пропуск для гостя на парковку?"
EXPERT_TEXT = "Отчёт о движении контингента сдаю до пятого числа, звоню секретарю кафедры."


def verdicts(*supported: bool) -> dict[str, Any]:
    return {"results": [{"idx": i, "supported": ok} for i, ok in enumerate(supported, start=1)]}


def set_rules(llm: FakeLLM, rules: list[dict[str, Any]]) -> None:
    llm.rules = [FakeRule.from_dict(r) for r in rules]


async def make_card(
    db: AsyncSession, world: dict[str, Any], title: str, summary: str, body: str, status: CardStatus
) -> KnowledgeCard:
    card = KnowledgeCard(
        handover_id=world["handover"].id,
        type="rule",
        title=title,
        summary=summary,
        body_md=body,
        origin=CardOrigin.INTERVIEW,
        status=status,
    )
    db.add(card)
    await db.flush()
    db.add(
        CardSource(
            card_id=card.id,
            source_type=SourceType.INTERVIEW_MESSAGE,
            source_id=world["message"].id,
            quote="сдаю до пятого числа",
        )
    )
    await db.flush()
    return card


@pytest.fixture
async def world(db: AsyncSession, app: FastAPI) -> dict[str, Any]:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    colleague = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    other_successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    handover = await make_handover(db, org_unit=unit, manager=manager, expert=expert, successor=successor)
    session = InterviewSession(handover_id=handover.id, expert_id=expert.id)
    db.add(session)
    await db.flush()
    message = InterviewMessage(session_id=session.id, seq=2, role=MessageRole.EXPERT, content=EXPERT_TEXT)
    db.add(message)
    await db.flush()
    w: dict[str, Any] = {"handover": handover, "message": message}
    report = await make_card(
        db,
        w,
        "Срок сдачи отчёта о движении контингента",
        "Отчёт о движении контингента сдают до 5-го числа каждого месяца.",
        "Отчёт отправляют в деканат по почте.",
        CardStatus.APPROVED,
    )
    signature = await make_card(
        db,
        w,
        "Нет подписи в ведомости — звонить секретарю кафедры",
        "Если в ведомости нет подписи экзаменатора, звонить секретарю кафедры.",
        "Телефон секретаря есть на сайте кафедры.",
        CardStatus.APPROVED,
    )
    draft = await make_card(
        db, w, "Черновик про контингент", "Отчёт о контингенте сдают до 1-го числа.", "", CardStatus.DRAFT
    )
    providers = app.state.providers
    for card in (report, signature, draft):
        await index_card(db, providers, card.id)
    await db.commit()
    return {**locals(), **w, "llm": providers.llm}


async def ask(client: httpx.AsyncClient, world: dict[str, Any], question: str) -> httpx.Response:
    return await client.post(
        "/api/assistant/ask", json={"handover_id": str(world["handover"].id), "question": question}
    )


async def test_only_approved_cards_are_indexed(db: AsyncSession, world: dict[str, Any]) -> None:
    indexed = set((await db.execute(select(CardChunk.card_id))).scalars())
    assert indexed == {world["report"].id, world["signature"].id}
    chunk = (await db.execute(select(CardChunk).where(CardChunk.card_id == world["report"].id))).scalar_one()
    assert chunk.text.startswith("Срок сдачи отчёта")


async def test_approval_and_edit_reindex_in_the_worker(
    client: httpx.AsyncClient, db: AsyncSession, app: FastAPI, world: dict[str, Any]
) -> None:
    draft_id, report_id = world["draft"].id, world["report"].id
    await login(client, world["expert"])
    assert (await client.post(f"/api/cards/{draft_id}/approve", json={})).status_code == 200
    count = select(func.count()).select_from(CardChunk).where(CardChunk.card_id == draft_id)
    assert await db.scalar(count) == 0  # indexing happens in the worker
    assert await jobs.run_one(get_sessionmaker(), get_settings(), app.state.providers)
    assert await db.scalar(count) == 1

    # Editing an approved card makes a new version, and the index follows it.
    assert (
        await client.patch(f"/api/cards/{report_id}", json={"summary": "Сдают до 7-го числа."})
    ).is_success
    assert await jobs.run_one(get_sessionmaker(), get_settings(), app.state.providers)
    db.expire_all()
    chunk = (await db.execute(select(CardChunk).where(CardChunk.card_id == report_id))).scalar_one()
    assert "до 7-го числа" in chunk.text and chunk.card_version == 2


async def test_answer_with_citations_is_verified_and_logged(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    set_rules(
        world["llm"],
        [
            {"match": VERIFY_PROMPT, "response_json": verdicts(True, True)},
            {
                "match": ANSWER_PROMPT,
                "response": "Отчёт сдают до 5-го числа каждого месяца [1]. "
                "Его отправляют в деканат по почте [1].",
            },
        ],
    )
    await login(client, world["successor"])
    body = (await ask(client, world, QUESTION)).json()
    assert body["status"] == "answered", body
    assert body["verification"] == "verified" and body["groundedness"] == 1.0
    assert body["answer"].endswith("по почте [1].")
    assert [s["title"] for s in body["sources"]] == ["Срок сдачи отчёта о движении контингента"]
    prompt = world["llm"].calls[0][0].content
    assert "Черновик" not in prompt  # drafts are never sources

    log = (await db.execute(select(QaLog))).scalar_one()
    assert log.cited_card_ids == [world["report"].id]
    assert log.retrieval["fts_hits"] > 0 and log.prompt_version == "answer@1+verify_claims@1"
    names = set((await db.execute(select(ProductEvent.name))).scalars())
    assert {"question_asked", "answer_shown"} <= names
    shown = (await db.execute(select(ProductEvent).where(ProductEvent.name == "answer_shown"))).scalar_one()
    assert QUESTION not in str(shown.props)  # metrics without the question text


async def test_unsupported_claims_are_removed(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    set_rules(
        world["llm"],
        [
            {"match": VERIFY_PROMPT, "response_json": verdicts(True, False)},
            {
                "match": ANSWER_PROMPT,
                "response": "Отчёт сдают до 5-го числа [1]. Опоздание грозит выговором [1].",
            },
        ],
    )
    await login(client, world["successor"])
    body = (await ask(client, world, QUESTION)).json()
    assert body["status"] == "partial"
    assert body["verification"] == "partially_removed" and body["groundedness"] == 0.5
    assert body["answer"] == "Отчёт сдают до 5-го числа [1]."


async def test_unrelated_question_is_refused_without_llm_and_becomes_a_gap(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    await login(client, world["successor"])
    body = (await ask(client, world, UNRELATED)).json()
    assert body["status"] == "refused" and body["refusal_reason"] == "no_relevant_sources"
    assert body["answer"] is None and body["sources"] == []
    assert body["forwarded_to"] == world["expert"].full_name
    assert world["llm"].calls == []

    gap = (await db.execute(select(Gap))).scalar_one()
    assert (gap.question, gap.assignee_id, gap.asked_by) == (
        UNRELATED,
        world["expert"].id,
        world["successor"].id,
    )
    # Asking again does not duplicate the open gap.
    await ask(client, world, UNRELATED + "  ")
    assert await db.scalar(select(func.count()).select_from(Gap)) == 1


async def test_llm_no_answer_and_all_claims_unsupported_are_refusals(
    client: httpx.AsyncClient, world: dict[str, Any]
) -> None:
    await login(client, world["successor"])
    set_rules(world["llm"], [{"match": ANSWER_PROMPT, "response": "NO_ANSWER"}])
    assert (await ask(client, world, QUESTION)).json()["refusal_reason"] == "llm_no_answer"
    set_rules(
        world["llm"],
        [
            {"match": VERIFY_PROMPT, "response_json": verdicts(False)},
            {"match": ANSWER_PROMPT, "response": "Отчёт сдают в любой день [1]."},
        ],
    )
    assert (await ask(client, world, QUESTION + " Точно?")).json()["refusal_reason"] == "unsupported"


async def test_without_a_model_the_found_cards_are_shown(
    client: httpx.AsyncClient, world: dict[str, Any]
) -> None:
    await login(client, world["successor"])  # the app FakeLLM has no rules → LLMError
    body = (await ask(client, world, QUESTION)).json()
    assert body["status"] == "answered" and body["verification"] == "degraded"
    assert "Модель сейчас недоступна" in body["answer"]
    assert "**Срок сдачи отчёта о движении контингента**" in body["answer"]


class BrokenJudge:
    name = model = "broken"

    async def complete_json(self, messages: list[Message], schema: Any, *, temperature: float = 0.0) -> Any:
        raise LLMError("judge is down")


async def test_judge_failure_keeps_the_answer_as_not_verified(
    client: httpx.AsyncClient, app: FastAPI, world: dict[str, Any]
) -> None:
    set_rules(world["llm"], [{"match": ANSWER_PROMPT, "response": "Отчёт сдают до 5-го числа [1]."}])
    app.state.providers.judge_llm = BrokenJudge()
    await login(client, world["successor"])
    body = (await ask(client, world, QUESTION)).json()
    assert (body["status"], body["verification"], body["groundedness"]) == ("answered", "not_verified", None)


async def test_feedback_and_history_are_personal(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    await login(client, world["successor"])
    qa_id = (await ask(client, world, UNRELATED)).json()["qa_id"]
    response = await client.post(
        f"/api/assistant/{qa_id}/feedback", json={"helpful": False, "comment": "мимо"}
    )
    assert response.json()["feedback"] == -1
    history = (
        await client.get("/api/assistant/history", params={"handover_id": str(world["handover"].id)})
    ).json()
    assert [h["qa_id"] for h in history] == [qa_id]

    await login(client, world["manager"])  # the manager can ask, but sees only their own history
    history = (
        await client.get("/api/assistant/history", params={"handover_id": str(world["handover"].id)})
    ).json()
    assert history == []
    assert (await client.post(f"/api/assistant/{qa_id}/feedback", json={"helpful": True})).status_code == 404


async def test_who_can_ask(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    for user in ("other_successor", "colleague", "expert"):
        await login(client, world[user])
        assert (await ask(client, world, QUESTION)).status_code == 403, user


async def test_gap_answer_becomes_a_card_and_closes_the_gap(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    hid = str(world["handover"].id)
    await login(client, world["successor"])
    await ask(client, world, UNRELATED)
    [gap] = (await client.get("/api/gaps", params={"handover_id": hid})).json()
    assert gap["status"] == "open" and gap["assignee_name"] == world["expert"].full_name

    await login(client, world["other_successor"])  # not a member
    assert (await client.get("/api/gaps", params={"handover_id": hid})).status_code == 403

    await login(client, world["expert"])
    answered = (
        await client.post(f"/api/gaps/{gap['id']}/answer", json={"text": "Пропуск заказывают у охраны."})
    ).json()
    assert answered["status"] == "open" and answered["answer_on_review"] is True
    again = await client.post(f"/api/gaps/{gap['id']}/answer", json={"text": "Ещё раз"})
    assert again.status_code == 409

    card = (await client.get(f"/api/cards/{answered['answered_card_id']}")).json()
    assert (card["status"], card["origin"], card["title"]) == ("draft", "gap_answer", UNRELATED)
    assert "Ответ эксперта на вопрос преемника" in card["sources"][0]["label"]

    # Rejecting the answer card reopens the gap for a new answer.
    await client.post(f"/api/cards/{card['id']}/reject", json={})
    reopened = (await client.get("/api/gaps", params={"handover_id": hid})).json()[0]
    assert reopened["status"] == "open" and reopened["answered_card_id"] is None

    second = (await client.post(f"/api/gaps/{gap['id']}/answer", json={"text": "У охраны на входе."})).json()
    assert (await client.post(f"/api/cards/{second['answered_card_id']}/approve", json={})).status_code == 200
    closed = (await client.get("/api/gaps", params={"handover_id": hid})).json()[0]
    assert closed["status"] == "answered" and closed["answered_at"] is not None
    names = list((await db.execute(select(ProductEvent.name))).scalars())
    assert "gap_created" in names and "gap_answered" in names


async def test_ask_expert_dismiss_and_reassign(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    hid = str(world["handover"].id)
    await login(client, world["successor"])
    created = await client.post(
        "/api/gaps", json={"handover_id": hid, "question": "Где лежат старые приказы?"}
    )
    assert created.status_code in (200, 201), created.text
    gap_id = created.json()["id"]

    await login(client, world["expert"])
    reassign = await client.patch(f"/api/gaps/{gap_id}", json={"assignee_id": str(world["colleague"].id)})
    assert reassign.status_code == 403  # only the manager reassigns

    await login(client, world["manager"])
    bad = await client.patch(f"/api/gaps/{gap_id}", json={"assignee_id": str(world["other_successor"].id)})
    assert bad.status_code == 400
    moved = (
        await client.patch(f"/api/gaps/{gap_id}", json={"assignee_id": str(world["colleague"].id)})
    ).json()
    assert moved["assignee_name"] == world["colleague"].full_name

    await login(client, world["colleague"])  # became an expert of the handover and can answer
    open_gaps = (await client.get("/api/gaps", params={"handover_id": hid, "status": "open"})).json()
    assert [g["id"] for g in open_gaps] == [gap_id]
    dismissed = (await client.post(f"/api/gaps/{gap_id}/dismiss")).json()
    assert dismissed["status"] == "dismissed"
    closed = await client.post(f"/api/gaps/{gap_id}/answer", json={"text": "Поздно"})
    assert closed.status_code == 409


async def test_gap_voice_answer_needs_consent(
    client: httpx.AsyncClient, db: AsyncSession, app: FastAPI, world: dict[str, Any]
) -> None:
    app.state.providers.asr = StubASR(duration_ms=3000)
    await login(client, world["successor"])
    await ask(client, world, UNRELATED)
    gap_id = (await db.execute(select(Gap.id))).scalar_one()
    upload = {"file": ("voice.webm", WEBM_AUDIO, "audio/webm")}

    await login(client, world["expert"])
    assert (await client.post(f"/api/gaps/{gap_id}/audio", files=upload)).status_code == 403
    await give_consent(db, world["expert"], world["handover"])
    await db.commit()
    response = await client.post(f"/api/gaps/{gap_id}/audio", files=upload)
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "Сначала открываю портал"
