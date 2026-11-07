from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.models import ProductEvent
from app.modules.identity.models import UserRole
from app.modules.interview.models import InterviewMessage, InterviewSession, MessageRole
from app.modules.knowledge.domain.sources import CardOrigin, SourceType
from app.modules.knowledge.models import CardRevision, CardSource, CardStatus, KnowledgeCard
from tests.factories import login, make_handover, make_org_unit, make_process, make_user

ANSWER = "Ведомость отправляю в деканат, только когда стоят все подписи экзаменаторов."


async def make_card(
    db: AsyncSession, handover_id: Any, message: InterviewMessage, title: str, **kw: Any
) -> KnowledgeCard:
    card = KnowledgeCard(
        handover_id=handover_id,
        type=kw.pop("type", "rule"),
        title=title,
        summary="Суть",
        body_md="Текст",
        origin=CardOrigin.INTERVIEW,
        **kw,
    )
    db.add(card)
    await db.flush()
    db.add(
        CardSource(
            card_id=card.id,
            source_type=SourceType.INTERVIEW_MESSAGE,
            source_id=message.id,
            quote="только когда стоят все подписи",
        )
    )
    await db.flush()
    return card


@pytest.fixture
async def world(db: AsyncSession) -> dict[str, Any]:
    unit = await make_org_unit(db)
    manager = await make_user(db, UserRole.MANAGER, org_unit=unit)
    expert = await make_user(db, UserRole.EXPERT, org_unit=unit)
    stranger = await make_user(db, UserRole.EXPERT, org_unit=unit)
    successor = await make_user(db, UserRole.SUCCESSOR, org_unit=unit)
    process = await make_process(db, unit, "Подготовка экзаменационных ведомостей")
    handover = await make_handover(
        db, org_unit=unit, manager=manager, expert=expert, successor=successor, processes=[process]
    )
    session = InterviewSession(handover_id=handover.id, expert_id=expert.id)
    db.add(session)
    await db.flush()
    message = InterviewMessage(session_id=session.id, seq=2, role=MessageRole.EXPERT, content=ANSWER)
    db.add(message)
    await db.flush()
    draft = await make_card(db, handover.id, message, "Когда отправлять ведомость")
    other = await make_card(db, handover.id, message, "Подписи в ведомости")
    approved = await make_card(db, handover.id, message, "Куда нести ведомость", status=CardStatus.APPROVED)
    await db.commit()
    return locals()


async def test_successor_sees_only_approved_cards_and_quotes(
    client: httpx.AsyncClient, world: dict[str, Any]
) -> None:
    await login(client, world["successor"])
    listed = (await client.get("/api/cards", params={"handover_id": str(world["handover"].id)})).json()
    assert [c["title"] for c in listed] == ["Куда нести ведомость"]
    assert (await client.get(f"/api/cards/{world['draft'].id}")).status_code == 404
    detail = (await client.get(f"/api/cards/{world['approved'].id}")).json()
    [source] = detail["sources"]
    assert source["quote"] == "только когда стоят все подписи"
    assert source["context"] is None  # no full transcript for successors
    assert source["available"] is True and "реплика 2" in source["label"]


async def test_expert_sees_source_context(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    await login(client, world["expert"])
    detail = (await client.get(f"/api/cards/{world['draft'].id}")).json()
    assert detail["sources"][0]["context"] == ANSWER
    assert detail["sources"][0]["link"]["session_id"] == str(world["session"].id)
    listed = (
        await client.get("/api/cards", params={"handover_id": str(world["handover"].id), "status": "draft"})
    ).json()
    assert len(listed) == 2


async def test_approve_with_edits_keeps_a_revision(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    await login(client, world["expert"])
    response = await client.post(
        f"/api/cards/{world['draft'].id}/approve",
        json={
            "edits": {
                "title": "Ведомость — только со всеми подписями",
                "process_id": str(world["process"].id),
            },
            "review_seconds": 42,
        },
    )
    body = response.json()
    assert (body["status"], body["version"], body["review_seconds"]) == ("approved", 2, 42)
    assert body["title"] == "Ведомость — только со всеми подписями"
    [revision] = (await db.execute(select(CardRevision))).scalars().all()
    assert (revision.version, revision.title) == (1, "Когда отправлять ведомость")
    [event] = (
        (await db.execute(select(ProductEvent).where(ProductEvent.name == "card_approved"))).scalars().all()
    )
    assert event.props["edited"] is True

    # Approving again is not allowed; editing an approved card makes a new version.
    assert (await client.post(f"/api/cards/{world['draft'].id}/approve", json={})).status_code == 400
    edited = (await client.patch(f"/api/cards/{world['draft'].id}", json={"summary": "Новая суть"})).json()
    assert edited["version"] == 3
    assert await db.scalar(select(func.count()).select_from(CardRevision)) == 2


async def test_approve_without_edits(
    client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]
) -> None:
    await login(client, world["expert"])
    body = (await client.post(f"/api/cards/{world['draft'].id}/approve", json={"review_seconds": 5})).json()
    assert (body["status"], body["version"]) == ("approved", 1)
    assert await db.scalar(select(func.count()).select_from(CardRevision)) == 0


async def test_reject_and_merge(client: httpx.AsyncClient, db: AsyncSession, world: dict[str, Any]) -> None:
    await login(client, world["expert"])
    rejected = (
        await client.post(f"/api/cards/{world['other'].id}/reject", json={"reason": "Неверно"})
    ).json()
    assert (rejected["status"], rejected["reject_reason"]) == ("rejected", "Неверно")

    merged = await client.post(
        f"/api/cards/{world['draft'].id}/merge", json={"into_card_id": str(world["approved"].id)}
    )
    assert (merged.json()["status"], merged.json()["archived_reason"]) == ("archived", "merged")
    # Same quote from the same message is not duplicated on the target.
    target_sources = (
        (await db.execute(select(CardSource).where(CardSource.card_id == world["approved"].id)))
        .scalars()
        .all()
    )
    assert len(target_sources) == 1
    bad = await client.post(
        f"/api/cards/{world['approved'].id}/merge", json={"into_card_id": str(world["other"].id)}
    )
    assert bad.status_code == 400


async def test_review_permissions(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    await login(client, world["stranger"])  # an expert of another handover
    assert (await client.get(f"/api/cards/{world['draft'].id}")).status_code == 403
    await login(client, world["manager"])
    assert (await client.get(f"/api/cards/{world['draft'].id}")).status_code == 200
    assert (await client.post(f"/api/cards/{world['draft'].id}/approve", json={})).status_code == 403
    await login(client, world["successor"])
    assert (await client.post(f"/api/cards/{world['approved'].id}/approve", json={})).status_code == 403


async def test_manual_card(client: httpx.AsyncClient, world: dict[str, Any]) -> None:
    await login(client, world["expert"])
    response = await client.post(
        "/api/cards",
        json={
            "handover_id": str(world["handover"].id),
            "type": "contact",
            "title": "Секретарь кафедры — подписи",
        },
    )
    assert response.status_code == 201
    assert (response.json()["origin"], response.json()["status"]) == ("manual", "draft")
